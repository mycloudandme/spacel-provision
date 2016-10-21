import unittest

from spacel.model import Orbit
from spacel.model.app import SpaceApp, SpaceDockerService

ORBIT_REGIONS = ('us-east-1', 'us-west-2')
CONTAINER = 'pwagner/elasticsearch-aws'
SERVICE_NAME = 'elasticsearch'


class TestSpaceApp(unittest.TestCase):
    def setUp(self):
        self.orbit = Orbit({
            'name': 'test-orbit',
            'regions': ORBIT_REGIONS
        })

    def test_constructor_default_regions(self):
        app = SpaceApp(self.orbit)
        self.assertEqual(ORBIT_REGIONS, app.regions)

    def test_constructor_custom_regions(self):
        app = SpaceApp(self.orbit, {
            'regions': ('us-east-1', 'us-west-1')
        })
        # us-west-1 is blocked since it's not in the orbit:
        self.assertEqual(['us-east-1'], app.regions)

    def test_public_ports_default(self):
        app = SpaceApp(self.orbit)

        self.assertEqual(1, len(app.public_ports))
        self.assertEqual('HTTP', app.public_ports[80].scheme)
        self.assertEquals(('0.0.0.0/0',), app.public_ports[80].sources)

    def test_public_ports_https(self):
        app = SpaceApp(self.orbit, {
            'public_ports': {
                443: {
                }
            }
        })
        self.assertEqual('HTTPS', app.public_ports[443].scheme)

    def test_public_ports_custom_sources(self):
        custom_sources = ('10.0.0.0/8', '192.168.0.0/16')
        app = SpaceApp(self.orbit, {
            'public_ports': {
                80: {
                    'sources': custom_sources
                }
            }
        })

        self.assertEqual('HTTP', app.public_ports[80].scheme)
        self.assertEquals(custom_sources, app.public_ports[80].sources)

    def test_services_docker(self):
        app = SpaceApp(self.orbit, {
            'services': {
                SERVICE_NAME: {
                    'image': CONTAINER,
                    'ports': {
                        9200: 9200,
                        9300: 9300
                    }
                }
            }
        })

        self.assertEqual(1, len(app.services))
        self.assertIsNotNone(app.services[SERVICE_NAME].unit_file)

    def test_services_units(self):
        app = SpaceApp(self.orbit, {
            'services': {
                SERVICE_NAME: {
                    'unit_file': '[Unit]'
                }
            }
        })

        self.assertEqual(1, len(app.services))
        self.assertEqual(app.services[SERVICE_NAME].unit_file, '[Unit]')

    def test_services_empty_unit(self):
        app = SpaceApp(self.orbit, {
            'services': {
                SERVICE_NAME: {}
            }
        })
        
        self.assertEqual(0, len(app.services))

    def test_spot(self):
        app = SpaceApp(self.orbit, {})

        spot_bool = {'spot': True}
        spot_string = {'spot': 'true'}
        spot_dict = {'spot': {'very': 'testy'}}
        self.assertEqual(app._spot(spot_bool), {})
        self.assertEqual(app._spot(spot_string), {})
        self.assertEqual(app._spot(spot_dict), spot_dict['spot'])

    def test_full_name(self):
        app = SpaceApp(self.orbit, {})
        self.assertEquals(app.full_name, 'test-orbit-test')


class TestSpaceDockerService(unittest.TestCase):
    def test_constructor_ports(self):
        service = SpaceDockerService(SERVICE_NAME,
                                     CONTAINER,
                                     ports={
                                         9200: 9200,
                                         9300: 9300
                                     })
        self.assertIn('-p 9200:9200', service.unit_file)
        self.assertIn('-p 9300:9300', service.unit_file)
        self.assertIn(' %s' % CONTAINER, service.unit_file)
        self.assertIn('elasticsearch.service', service.name)
