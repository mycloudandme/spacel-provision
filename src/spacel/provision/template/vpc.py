from copy import deepcopy

from spacel.model.orbit import NAT_PER_AZ, PRIVATE_NETWORK, PRIVATE_NAT_GATEWAY
from spacel.provision.template.base import BaseTemplateCache


class VpcTemplate(BaseTemplateCache):
    def __init__(self):
        super(VpcTemplate, self).__init__()

    def vpc(self, orbit, region):
        """
        Get customized template for VPC.
        :param orbit:  Orbit.
        :param region: Region.
        :return: VPC template.
        """
        vpc_template = self.get('vpc')
        params = vpc_template['Parameters']

        nat_per_az = orbit.get_param(region, NAT_PER_AZ)
        params['NatPerAz']['Default'] = nat_per_az and 'true' or 'false'

        params['VpcCidr']['Default'] = orbit.get_param(region, PRIVATE_NETWORK)

        azs = orbit.azs(region)
        if not azs:
            return vpc_template
        resources = vpc_template['Resources']
        outputs = vpc_template['Outputs']

        base_az = params['Az01']
        base_az['Default'] = azs[0]

        private_nat_gateway = orbit.get_param(
            region, PRIVATE_NAT_GATEWAY) == 'enabled'

        base_nat_eip = resources['NatEip01']
        base_nat_gateway = resources['NatGateway01']
        base_default_route = resources['PrivateRouteTable01DefaultRoute']

        for index, az in enumerate(azs[1:]):
            az_index = (index + 2)
            az_param = 'Az%02d' % az_index

            # Each AZ should be declared as a parameter:
            params[az_param] = deepcopy(base_az)
            params[az_param]['Description'] = 'Generated AZ parameter.'
            params[az_param]['Default'] = az

            # Replicate route tables:
            rt_clone = deepcopy(resources['PrivateRouteTable01'])
            rt_name = self._get_name_tag(rt_clone['Properties'])
            rt_name['Fn::Join'][1][1] = 'Private%02d' % az_index
            private_rt_resource = 'PrivateRouteTable%02d' % az_index
            resources[private_rt_resource] = rt_clone

            # Replicate subnets:
            self._add_subnet(resources, outputs, az_index, az_param,
                             'PublicInstance', az_index)
            self._add_subnet(resources, outputs, az_index, az_param,
                             'PublicElb', 20 + az_index)
            nat_subnet_resource = self._add_subnet(resources, None,
                                                   az_index, az_param,
                                                   'PublicNat',
                                                   40 + az_index)
            self._add_subnet(resources, outputs, az_index, az_param,
                             'PublicRds', 80 + az_index)
            self._add_subnet(resources, outputs, az_index, az_param,
                             'PrivateInstance', 100 + az_index,
                             private_rt_resource)
            self._add_subnet(resources, outputs, az_index, az_param,
                             'PrivateElb', 120 + az_index,
                             private_rt_resource)
            self._add_subnet(resources, outputs, az_index, az_param,
                             'PrivateCache', 160 + az_index,
                             private_rt_resource)
            self._add_subnet(resources, outputs, az_index, az_param,
                             'PrivateRds', 180 + az_index, private_rt_resource)

            if private_nat_gateway:
                # Each AZ _can_ have a NAT gateway:
                nat_eip_clone = deepcopy(base_nat_eip)
                nat_eip_clone['Condition'] = 'MultiAzNat'
                nat_eip_resource = 'NatEip%02d' % az_index
                resources[nat_eip_resource] = nat_eip_clone
                outputs[nat_eip_resource] = {
                    'Value': {'Fn::If': ['MultiAzNat',
                                         {'Ref': nat_eip_resource}, '']}
                }

                # Each AZ _can_ have a NAT gateway:
                nat_gateway_clone = deepcopy(base_nat_gateway)
                nat_gateway_clone['Condition'] = 'MultiAzNat'
                nat_gateway_props = nat_gateway_clone['Properties']
                nat_gateway_props['SubnetId']['Ref'] = nat_subnet_resource
                nat_gateway_props['AllocationId']['Fn::GetAtt'][0] = \
                    nat_eip_resource
                nat_gateway_resource = 'NatGateway%02d' % az_index
                resources[nat_gateway_resource] = nat_gateway_clone

                # Each private route table has a default NAT route:
                private_default_route_clone = deepcopy(base_default_route)
                private_route_props = private_default_route_clone['Properties']
                private_route_props['RouteTableId']['Ref'] = private_rt_resource
                private_route_props['NatGatewayId'] = {
                    'Fn::If': [
                        'MultiAzNat', {'Ref': nat_gateway_resource},
                        {'Ref': 'NatGateway01'}
                    ]
                }
                private_route_resource = 'PrivateRouteTable%02dDefaultRoute' % \
                                         az_index
                resources[private_route_resource] = private_default_route_clone

        self._add_subnet_ids(resources, azs, 'PrivateCache')
        self._add_subnet_ids(resources, azs, 'PublicRds')
        self._add_subnet_ids(resources, azs, 'PrivateRds')

        if not private_nat_gateway:
            private_route_table_default_route = (
                resources['PrivateRouteTable01DefaultRoute']['Properties'])
            del (resources['NatGateway01'], resources['NatEip01'],
                 resources['PrivateRouteTable01DefaultRoute'],
                 private_route_table_default_route['NatGatewayId'])
            private_route_table_default_route['GatewayId'] = {
                'Ref': 'InternetGateway'
            }
            outputs['NatEip01']['Value'] = ''

        return vpc_template

    def _add_subnet(self, resources, outputs, az_index, az, label, cidr,
                    rt=None):
        subnet_resource = '%sSubnet%02d' % (label, az_index)
        subnet_clone = deepcopy(resources['%sSubnet01' % label])
        subnet_props = subnet_clone['Properties']
        subnet_props['CidrBlock']['Fn::Join'][1][1] = '.%d.0/24' % cidr
        subnet_props['AvailabilityZone']['Ref'] = az
        subnet_name = self._get_name_tag(subnet_props)
        subnet_name['Fn::Join'][1][1] = '%s%02d' % (label, az_index)

        resources[subnet_resource] = subnet_clone
        if outputs:
            outputs[subnet_resource] = {
                'Value': {'Ref': subnet_resource}
            }

        base_rta = '%sSubnet01RouteTableAssociation' % label
        rta_clone = deepcopy(resources[base_rta])
        rta_props = rta_clone['Properties']
        rta_props['SubnetId']['Ref'] = subnet_resource
        if rt:
            rta_props['RouteTableId']['Ref'] = rt

        rta_resource = '%sSubnet%02dRouteTableAssociation' % (
            label, az_index)
        resources[rta_resource] = rta_clone
        return subnet_resource

    @staticmethod
    def _add_subnet_ids(resources, azs, label):
        subnet_group = resources.get('%sSubnetGroup' % label, {})
        subnet_ids = subnet_group.get('Properties', {}).get('SubnetIds', [])
        for index, _ in enumerate(azs[1:]):
            subnet_ids.append({'Ref': '%sSubnet%02d' % (label, index + 2)})
