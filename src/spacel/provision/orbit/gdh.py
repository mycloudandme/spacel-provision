from botocore.exceptions import ClientError
import logging
from spacel.provision.cloudformation import (BaseCloudFormationFactory,
                                             key_sorted)
from spacel.model.orbit import GDH_DEPLOY, GDH_PARENT

logger = logging.getLogger('spacel.provision.orbit.gdh')


class GitDeployHooksOrbitFactory(BaseCloudFormationFactory):
    """
    Queries existing orbital VPCs built by git-deploy.
    """
    def get_orbit(self, orbit, regions=None):
        regions = regions or orbit.regions
        for region in regions:
            parent_stack_name = orbit.get_param(region, GDH_PARENT)
            deploy_stack_name = orbit.get_param(region, GDH_DEPLOY)
            cf = self._clients.cloudformation(region)

            # Check for parent in region:
            name = orbit.name
            logger.debug('Querying %s in %s...', name, region)
            try:
                parent_resource = cf.describe_stack_resource(
                    StackName=parent_stack_name, LogicalResourceId=name)
            except ClientError as e:
                e_message = e.response['Error'].get('Message', '')
                if 'does not exist' in e_message:
                    logger.warn('Orbit %s not found in %s.', name, region)
                    continue
                raise e

            # Parent found, query child:
            child_resource_id = (parent_resource
                                 ['StackResourceDetail']
                                 ['PhysicalResourceId'])
            logger.debug('Querying %s for outputs...', child_resource_id)
            child_stack = self._describe_stack(cf, child_resource_id)
            parameters = child_stack.get('Parameters', ())
            outputs = child_stack.get('Outputs', ())

            self._orbit_from_child(orbit, region, name, parameters, outputs)

            deploy_stack = self._describe_stack(cf, deploy_stack_name)
            outputs = deploy_stack.get('Outputs', ())
            for output in outputs:
                key = output['OutputKey']
                value = output['OutputValue']
                if key == 'SecurityGroup':
                    orbit._bastion_sgs[region] = value

    @staticmethod
    def _orbit_from_child(orbit, region, name, cf_parameters, cf_outputs):
        # Map parameters onto orbit model:
        azs = []
        for parameter in cf_parameters:
            key = parameter['ParameterKey']
            value = parameter['ParameterValue']
            if key.startswith('Az'):
                azs.append(value)
        azs = sorted(azs)
        orbit._azs[region] = azs

        # Map outputs onto orbit model:
        private_subnets = {}
        public_subnets = {}
        for output in cf_outputs:
            key = output['OutputKey']
            value = output['OutputValue']
            if key.startswith('PrivateSubnet'):
                private_subnets[key[-2:]] = value
            elif key.startswith('PublicSubnet'):
                public_subnets[key[-2:]] = value
            elif key.startswith('NATElasticIP'):
                orbit._nat_eips[region][key[-2:]] = value
            elif key.startswith('EnvironmentVpcId'):
                orbit._vpc_ids[region] = value
            elif key.startswith('PrivateCacheSubnetGroup'):
                orbit._private_cache_subnet_groups[region] = value
            elif key.startswith('PublicRdsSubnetGroup'):
                orbit._public_rds_subnet_groups[region] = value
            elif key.startswith('PrivateRdsSubnetGroup'):
                orbit._private_rds_subnet_groups[region] = value
            elif key.startswith('RoleSpotFleet'):
                orbit._spot_fleet_role[region] = value
            elif key.startswith('PublicRouteTable'):
                continue
            elif key.startswith('PrivateRouteTable'):
                continue
            elif key == 'CIDR':
                continue
            else:
                logger.warn('Unrecognized output key: %s', key)
        public_subnets = key_sorted(public_subnets)
        private_subnets = key_sorted(private_subnets)
        orbit._public_instance_subnets[region] = public_subnets
        orbit._public_elb_subnets[region] = public_subnets
        orbit._private_instance_subnets[region] = private_subnets
        orbit._private_elb_subnets[region] = private_subnets
        logger.debug('Updated %s in %s.', name, region)
        logger.debug('Azs: %s, %s public subnets, %s private subnets.',
                     azs, len(public_subnets), len(private_subnets))
