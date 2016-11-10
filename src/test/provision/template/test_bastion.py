import unittest

from mock import MagicMock

from spacel.aws import AmiFinder
from spacel.model import Orbit
from spacel.model.orbit import BASTION_INSTANCE_COUNT
from spacel.provision.template.bastion import BastionTemplate
from test import REGION
from test.provision.template import SUBNETS

DOMAIN = 'bastion'


class TestBastionTemplate(unittest.TestCase):
    def setUp(self):
        self.ami_finder = MagicMock(spec=AmiFinder)
        self.cache = BastionTemplate(self.ami_finder)
        base_template = self.cache.get('asg-bastion')
        self.base_resources = len(base_template['Resources'])
        self.orbit = Orbit({})
        self.orbit._public_instance_subnets = {REGION: SUBNETS}

    def test_no_bastion(self):
        self.orbit._params[REGION] = {BASTION_INSTANCE_COUNT: 0}
        bastion = self.cache.bastion(self.orbit, REGION)

        self.assertEquals(bastion, False)

    def test_bastion(self):
        bastion = self.cache.bastion(self.orbit, REGION)

        bastion_resources = len(bastion['Resources'])
        self.assertEquals(self.base_resources, bastion_resources)

    def test_bastion_multi_eip(self):
        self.orbit._params[REGION] = {BASTION_INSTANCE_COUNT: 2}

        bastion = self.cache.bastion(self.orbit, REGION)

        bastion_resources = bastion['Resources']
        # 3 resources: Eip01, DNS:bastion01, DNS:bastion02
        self.assertEquals(self.base_resources + 3, len(bastion_resources))
        self.assertIn('ElasticIp02', bastion_resources)
        self.assertIn('DnsRecord02', bastion_resources)

    def test_bastion_domain(self):
        self.orbit.domain = DOMAIN
        bastion = self.cache.bastion(self.orbit, REGION)

        bastion_params = bastion['Parameters']
        self.assertEqual(
            'bastion.', bastion_params['VirtualHostDomain']['Default'])
