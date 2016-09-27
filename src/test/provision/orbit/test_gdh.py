from botocore.exceptions import ClientError
from mock import MagicMock
import unittest

from spacel.aws import ClientCache
from spacel.provision.changesets import ChangeSetEstimator
from spacel.model import Orbit
from spacel.model.orbit import (GDH_DEPLOY, GDH_PARENT)
from spacel.provision.orbit.gdh import GitDeployHooksOrbitFactory
from spacel.provision.s3 import TemplateUploader
from test.provision.orbit import (NAME, REGION, VPC_ID, IP_ADDRESS, cf_outputs,
                                  cf_parameters)

PARENT_NAME = 'daddy'
DEPLOY_NAME = 'deploy'
STACK_ID = 'arn:cloudformation:123456'
ROLE_SPOT_FLEET = 'arn:iam:role:123456'


class TestGitDeployHooksOrbitFactory(unittest.TestCase):
    def setUp(self):
        self.clients = MagicMock(spec=ClientCache)
        self.cloudformation = MagicMock()
        self.cloudformation.describe_stack_resource.return_value = {
            'StackResourceDetail': {
                'PhysicalResourceId': STACK_ID
            }
        }
        self.clients.cloudformation.return_value = self.cloudformation
        self.orbit = Orbit({
            'name': NAME,
            'regions': (REGION,),
            REGION: {
                GDH_DEPLOY: PARENT_NAME,
                GDH_PARENT: DEPLOY_NAME
            }
        })

        self.change_sets = MagicMock(spec=ChangeSetEstimator)
        self.templates = MagicMock(spec=TemplateUploader)
        self.orbit_factory = GitDeployHooksOrbitFactory(self.clients,
                                                        self.change_sets,
                                                        self.templates)
        self.orbit_factory._describe_stack = MagicMock()

    def test_get_orbit(self):
        self.orbit_factory._orbit_from_child = MagicMock()

        self.orbit_factory.get_orbit(self.orbit)

        self.cloudformation.describe_stack_resource.assert_called_once()
        self.orbit_factory._orbit_from_child.assert_called_once()

    def test_get_orbit_not_found(self):
        self._describe_stack_resource_error('Stack does not exist')
        self.orbit_factory._orbit_from_child = MagicMock()

        self.orbit_factory.get_orbit(self.orbit)

        self.orbit_factory._orbit_from_child.assert_not_called()

    def test_get_orbit_error(self):
        self._describe_stack_resource_error('kaboom')

        self.assertRaises(ClientError, self.orbit_factory.get_orbit, self.orbit)

    def _describe_stack_resource_error(self, message):
        self.cloudformation.describe_stack_resource.side_effect = ClientError({
            'Error': {
                'Message': message
            }
        }, 'CreateSubnet')

    def test_orbit_from_child(self):
        params = {
            'Az1': 'us-west-2a',
            'Az2': 'us-west-2b',
            'Az3': 'us-west-2c',
        }
        outputs = {
            'PrivateSubnet01': 'subnet-000001',
            'PrivateSubnet02': 'subnet-000002',
            'PublicSubnet01': 'subnet-000101',
            'PublicRouteTable': 'rtb-000001',
            'PrivateRouteTable': 'rtb-000002',
            'NATElasticIP01': IP_ADDRESS,
            'EnvironmentVpcId': VPC_ID,
            'PrivateCacheSubnetGroup': 'subnet-000000',
            'PublicRdsSubnetGroup': 'subnet-000000',
            'PrivateRdsSubnetGroup': 'subnet-000000',
            'RoleSpotFleet': ROLE_SPOT_FLEET,
            'CIDR': '%s/32' % IP_ADDRESS,
            'Unknown': 'AndThatsOk'
        }

        self.orbit_factory._orbit_from_child(self.orbit, REGION, NAME,
                                             cf_parameters(params),
                                             cf_outputs(outputs))

        self.assertEquals(['subnet-000001', 'subnet-000002'],
                          self.orbit.private_instance_subnets(REGION))
        self.assertEquals(['subnet-000001', 'subnet-000002'],
                          self.orbit.private_elb_subnets(REGION))
        self.assertEquals(['subnet-000101'],
                          self.orbit.public_instance_subnets(REGION))
        self.assertEquals(['subnet-000101'],
                          self.orbit.public_elb_subnets(REGION))
        self.assertEquals(VPC_ID, self.orbit.vpc_id(REGION))
        self.assertEquals(ROLE_SPOT_FLEET, self.orbit.spot_fleet_role(REGION))
        self.assertEquals('subnet-000000',
                          self.orbit.public_rds_subnet_group(REGION))
        self.assertEquals('subnet-000000',
                          self.orbit.private_rds_subnet_group(REGION))
        self.assertEquals('subnet-000000',
                          self.orbit.private_cache_subnet_group(REGION))
        self.assertEquals(['us-west-2a', 'us-west-2b', 'us-west-2c'],
                          self.orbit.azs(REGION))
