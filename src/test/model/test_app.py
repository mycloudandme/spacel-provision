from mock import MagicMock

from spacel.model.app import SpaceApp, SpaceAppRegion, SpaceServicePort
from test import BaseSpaceAppTest, APP_NAME, ORBIT_REGION

CONTAINER = 'pwagner/elasticsearch-aws'
SERVICE_NAME = 'elasticsearch.service'
SERVICE_NAME_NO_EXT = 'elasticsearch'


class TestSpaceApp(BaseSpaceAppTest):
    def test_default_regions(self):
        """When no regions are specified, use orbit regions."""
        self.assertEqual({ORBIT_REGION}, set(self.app.regions.keys()))

    def test_custom_regions(self):
        self.app = SpaceApp(self.orbit, APP_NAME, [ORBIT_REGION, 'meow'])
        self.assertEqual({ORBIT_REGION}, set(self.app.regions.keys()))

    def test_valid(self):
        self.assertTrue(self.app.valid)

    def test_valid_no_name(self):
        self.app.name = None
        self.assertFalse(self.app.valid)

    def test_valid_no_regions(self):
        self.app.regions = {}
        self.assertFalse(self.app.valid)

    def test_valid_invalid_region(self):
        invalid_region = MagicMock(spec=SpaceAppRegion)
        invalid_region.valid = False
        self.app.regions[ORBIT_REGION] = invalid_region
        self.assertFalse(self.app.valid)

    def test_full_name(self):
        self.assertEquals(self.app.full_name, 'test-orbit-test-app')


class TestSpaceAppRegion(BaseSpaceAppTest):
    def test_valid(self):
        self.assertTrue(self.app_region.valid)

    def test_valid_invalid_elb_availability(self):
        self.app_region.elb_availability = 'meow'
        self.assertFalse(self.app_region.valid)

    def test_valid_invalid_instance_availability(self):
        self.app_region.instance_availability = 'meow'
        self.assertFalse(self.app_region.valid)

    def test_valid_invalid_update_policy(self):
        self.app_region.update_policy = 'meow'
        self.assertFalse(self.app_region.valid)

    def test_load_balancer_true(self):
        self.app_region.elb_availability = 'internet-facing'
        self.assertTrue(self.app_region.load_balancer)

    def test_load_balancer_false(self):
        self.app_region.elb_availability = 'disabled'
        self.assertFalse(self.app_region.load_balancer)

    def test_elb_public_true(self):
        self.app_region.elb_availability = 'internet-facing'
        self.assertTrue(self.app_region.elb_public)

    def test_elb_public_false(self):
        self.app_region.elb_availability = 'disabled'
        self.assertFalse(self.app_region.elb_public)

    def test_instance_public_true(self):
        self.app_region.instance_availability = 'internet-facing'
        self.assertTrue(self.app_region.elb_public)

    def test_instance_public_false(self):
        self.app_region.instance_availability = 'disabled'
        self.assertFalse(self.app_region.instance_public)


class TestSpaceServicePort(BaseSpaceAppTest):
    def test_port_443_http(self):
        port = SpaceServicePort(port=443)
        self.assertEquals('HTTPS', port.scheme)
