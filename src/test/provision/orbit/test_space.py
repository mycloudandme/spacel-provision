from botocore.exceptions import ClientError
from mock import MagicMock
import unittest

from spacel.aws import ClientCache
from spacel.model import Orbit
from spacel.provision.changesets import ChangeSetEstimator
from spacel.provision.template import (VpcTemplate, BastionTemplate,
                                       TablesTemplate)
from spacel.provision.orbit.space import SpaceElevatorOrbitFactory
from spacel.provision.s3 import TemplateUploader

from test.provision.orbit import (NAME, REGION, VPC_ID, IP_ADDRESS, cf_outputs)

SECURITY_GROUP_ID = 'sg-123456'
SPOTFLEET_ROLE_ARN = 'arn:aws:iam::1234567890:role/spot-fleet-role'


class TestSpaceElevatorOrbitFactory(unittest.TestCase):
    def setUp(self):
        self.vpc_template = MagicMock(spec=VpcTemplate)
        self.vpc_template.vpc.return_value = {}
        self.bastion_template = MagicMock(spec=BastionTemplate)
        self.bastion_template.bastion.return_value = {}
        self.tables_template = MagicMock(spec=TablesTemplate)
        self.tables_template.tables.return_value = {}
        self.clients = MagicMock(spec=ClientCache)
        self.change_sets = MagicMock(spec=ChangeSetEstimator)
        self.templates = MagicMock(spec=TemplateUploader)
        self.ec2 = MagicMock()
        self.clients.ec2.return_value = self.ec2
        self.orbit = Orbit({
            'name': NAME,
            'regions': (REGION,)
        })
        self.orbit_factory = SpaceElevatorOrbitFactory(self.clients,
                                                       self.change_sets,
                                                       self.templates,
                                                       self.vpc_template,
                                                       self.bastion_template,
                                                       self.tables_template)

    def test_get_orbit(self):
        self.orbit._bastion_eips[REGION] = {'01': IP_ADDRESS}

        self.orbit_factory._azs = MagicMock()
        self.orbit_factory._orbit_stack = MagicMock()

        self.orbit_factory.get_orbit(self.orbit, self.orbit.regions)

        self.orbit_factory._azs.assert_called_once()
        self.assertEquals(3, self.orbit_factory._orbit_stack.call_count)

    def test_orbit_stack_vpc_noop(self):
        self.orbit_factory._stack = MagicMock(return_value=None)
        self.orbit_factory._wait_for_updates = MagicMock()
        self.orbit_factory._orbit_from_vpc = MagicMock()
        self.orbit_factory._orbit_from_bastion = MagicMock()

        self.orbit_factory._orbit_stack(self.orbit, self.orbit.regions, 'vpc')

        self.vpc_template.vpc.assert_called_once_with(self.orbit, REGION)
        self.orbit_factory._wait_for_updates.assert_called_once()
        self.orbit_factory._orbit_from_vpc.assert_called_once()
        self.orbit_factory._orbit_from_bastion.assert_not_called()

    def test_orbit_stack_bastion_update(self):
        self.orbit_factory._stack = MagicMock(return_value='update')
        self.orbit_factory._wait_for_updates = MagicMock()
        self.orbit_factory._orbit_from_vpc = MagicMock()
        self.orbit_factory._orbit_from_bastion = MagicMock()

        self.orbit_factory._orbit_stack(self.orbit, self.orbit.regions,
                                        'bastion')

        self.vpc_template.vpc.assert_not_called()
        self.bastion_template.bastion.assert_called_once_with(self.orbit,
                                                              REGION)
        self.orbit_factory._wait_for_updates.assert_called_once()
        self.orbit_factory._orbit_from_vpc.assert_not_called()
        self.orbit_factory._orbit_from_bastion.assert_called_once()

    def test_orbit_stack_tables_noop(self):
        self.orbit_factory._stack = MagicMock(return_value=None)
        self.orbit_factory._wait_for_updates = MagicMock()
        self.orbit_factory._orbit_from_vpc = MagicMock()
        self.orbit_factory._orbit_from_bastion = MagicMock()

        self.orbit_factory._orbit_stack(self.orbit, self.orbit.regions,
                                        'tables')

        self.tables_template.tables.assert_called_once_with(self.orbit)
        self.orbit_factory._orbit_from_vpc.assert_not_called()
        self.orbit_factory._orbit_from_bastion.assert_not_called()

    def test_orbit_stack_unknown(self):
        self.orbit_factory._stack = MagicMock()
        self.orbit_factory._wait_for_updates = MagicMock()

        self.orbit_factory._orbit_stack(self.orbit, self.orbit.regions,
                                        'kaboom')

        self.orbit_factory._stack.assert_not_called()
        self.orbit_factory._wait_for_updates.assert_not_called()

    def test_azs(self):
        self._create_subnet_error(
            'us-east-1zzz is invalid. Subnets can currently only be created in '
            'the following availability zones: us-east-1a, us-east-1b')

        self.orbit_factory._azs(self.orbit, self.orbit.regions)

        self.clients.ec2.assert_called_once_with(REGION)
        self.ec2.create_subnet.assert_called_once()
        self.assertEquals(['us-east-1a', 'us-east-1b'], self.orbit.azs(REGION))

    def test_azs_error(self):
        self._create_subnet_error('Kaboom')
        self.assertRaises(ClientError, self.orbit_factory._azs, self.orbit,
                          self.orbit.regions)

    def _create_subnet_error(self, message):
        self.ec2.create_subnet.side_effect = ClientError({
            'Error': {
                'Message': message
            }
        }, 'CreateSubnet')

    def test_orbit_from_vpc(self):
        outputs = {
            'PrivateInstanceSubnet01': 'subnet-000001',
            'PrivateInstanceSubnet02': 'subnet-000002',
            'PrivateElbSubnet01': 'subnet-000012',
            'PrivateElbSubnet02': 'subnet-000011',
            'PublicInstanceSubnet': 'subnet-000101',
            'PublicElbSubnet': 'subnet-000111',
            'PublicNatSubnet': 'subnet-000121',
            'NatEip': IP_ADDRESS,
            'VpcId': VPC_ID,
            'PublicRdsSubnetGroup': 'public-rds',
            'PrivateRdsSubnetGroup': 'private-rds',
            'PrivateCacheSubnetGroup': 'private-rds',
            'PrivateCacheSubnet01': 'subnet-666666',
            'PrivateRdsSubnet01': 'subnet-777777',
            'RoleSpotFleet': SPOTFLEET_ROLE_ARN,
            'Unknown': 'AndThatsOk'

        }

        self.orbit_factory._orbit_from_vpc(self.orbit, REGION,
                                           cf_outputs(outputs))

        self.assertEquals(['subnet-000001', 'subnet-000002'],
                          self.orbit.private_instance_subnets(REGION))
        self.assertEquals(['subnet-000012', 'subnet-000011'],
                          self.orbit.private_elb_subnets(REGION))
        self.assertEquals(['subnet-000101'],
                          self.orbit.public_instance_subnets(REGION))
        self.assertEquals(['subnet-000111'],
                          self.orbit.public_elb_subnets(REGION))
        self.assertEquals(VPC_ID, self.orbit.vpc_id(REGION))
        self.assertEquals(SPOTFLEET_ROLE_ARN,
                          self.orbit.spot_fleet_role(REGION))
        self.assertEquals('private-rds',
                          self.orbit.private_rds_subnet_group(REGION))

    def test_orbit_from_bastion(self):
        outputs = {
            'ElasticIp01': IP_ADDRESS,
            'ElasticIp02': '127.0.0.2',
            'BastionSecurityGroup': SECURITY_GROUP_ID,
            'Unknown': 'AndThatsOk'
        }

        self.orbit_factory._orbit_from_bastion(self.orbit, REGION,
                                               cf_outputs(outputs))

        self.assertEquals(SECURITY_GROUP_ID, self.orbit.bastion_sg(REGION))
        self.assertEquals({'01': IP_ADDRESS, '02': '127.0.0.2'},
                          self.orbit.bastion_eips(REGION))
