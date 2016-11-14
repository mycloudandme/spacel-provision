import unittest

from spacel.model import Orbit
from spacel.provision.template.vpc import VpcTemplate

REGION = 'us-east-1'
AZA = 'us-east-1a'
AZB = 'us-east-1b'


class TestVpcTemplate(unittest.TestCase):
    def setUp(self):
        self.cache = VpcTemplate()
        base_template = self.cache.get('vpc')
        self.base_resources = len(base_template['Resources'])
        self.orbit = Orbit({})

    def test_vpc_no_az(self):
        vpc = self.cache.vpc(self.orbit, REGION)

        # No resources injected:
        vpc_resources = len(vpc['Resources'])
        self.assertEquals(self.base_resources, vpc_resources)

    def test_vpc_no_private_nat_gateway(self):
        args = {'private_nat_gateway': 'disabled'}
        self.orbit._azs = {REGION: [AZA, AZB]}
        self.orbit._params = {REGION: args}
        vpc = self.cache.vpc(self.orbit, REGION)

        # No nat gateway injected
        vpc_resources = vpc['Resources']

        self.assertNotIn('NatGateway01', vpc_resources)

    def test_vpc(self):
        self.vpc_regions('us-east-1a', 'us-east-1b')
        self.vpc_regions('us-east-1a', 'us-east-1b', 'us-east-1c')
        self.vpc_regions('us-east-1a', 'us-east-1b', 'us-east-1c', 'us-east-1d')

    def vpc_regions(self, *args):
        self.orbit._azs = {REGION: args}
        vpc = self.cache.vpc(self.orbit, REGION)
        # For N AZs, N-1 resources are injected:
        injected_resources = len(vpc['Resources']) - self.base_resources
        self.assertEquals(0, injected_resources % (len(args) - 1))
