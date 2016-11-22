import json

from spacel.model.json.app import SpaceAppJsonModelFactory
from spacel.model.json.base import NAME, REGIONS, ALL
from test import BaseSpaceAppTest, ORBIT_REGION, APP_NAME

CONTAINER = 'pebbletech/spacel-laika'
SERVICE_NAME = 'laika.service'
SERVICE_NAME_NO_EXT = 'laika'
FILE_NAME = 'test-file'
SIMPLE_UNIT = '[Unit]'


class TestSpaceAppJsonModelFactory(BaseSpaceAppTest):
    def setUp(self):
        super(TestSpaceAppJsonModelFactory, self).setUp()
        self.factory = SpaceAppJsonModelFactory()
        self.params = {
            NAME: APP_NAME,
            REGIONS: [ORBIT_REGION],
            ALL: {
                'instance_type': 't2.micro'
            }
        }

    def test_app_no_regions(self):
        """When app doesn't specify regions, all orbit regions."""
        del self.params[REGIONS]
        app = self.factory.app(self.orbit, self.params)
        self.assertEquals({ORBIT_REGION}, set(app.regions.keys()))
        self.assertTrue(app.valid)

    def test_app_region_not_in_orbit(self):
        """Valid region that isn't part of orbit is dropped."""
        self.params[REGIONS] += ['eu-west-1']
        app = self.factory.app(self.orbit, self.params)
        self.assertEquals({ORBIT_REGION}, set(app.regions.keys()))
        self.assertTrue(app.valid)

    def test_app_elastic_ips(self):
        self.params['all']['elastic_ips'] = 'true'
        app = self.factory.app(self.orbit, self.params)
        app_region = app.regions[ORBIT_REGION]
        self.assertTrue(app_region.elastic_ips)

    def test_app_elastic_ips_disabled(self):
        self.params['all']['elastic_ips'] = 'false'
        app = self.factory.app(self.orbit, self.params)
        app_region = app.regions[ORBIT_REGION]
        self.assertFalse(app_region.elastic_ips)

    def test_app_services_docker(self):
        app_region = self._services({
            'image': CONTAINER,
            'ports': {
                9200: 9200,
                9300: 9300
            }
        })

        self.assertEqual(1, len(app_region.services))
        self.assertIsNotNone(app_region.services[SERVICE_NAME].unit_file)

    def test_services_service_extension(self):
        app_region = self._services({
            'unit_file': SIMPLE_UNIT
        }, service_name=SERVICE_NAME_NO_EXT)

        self.assertEqual(1, len(app_region.services))
        self.assertEqual(app_region.services[SERVICE_NAME].unit_file,
                         SIMPLE_UNIT)

    def test_services_units(self):
        app_region = self._services({
            'unit_file': SIMPLE_UNIT
        })

        self.assertEqual(1, len(app_region.services))
        self.assertIsNotNone(app_region.services[SERVICE_NAME].unit_file)

    def test_services_empty_unit(self):
        app_region = self._services({})
        self.assertEqual(0, len(app_region.services))

    def test_services_invalid_unit(self):
        app_region = self._services({'foo': 'bar'})
        self.assertEqual(0, len(app_region.services))

    def _services(self, params, service_name=SERVICE_NAME):
        app = self.factory.app(self.orbit, {
            ALL: {
                'services': {
                    service_name: params
                }
            }
        })
        app_region = app.regions[ORBIT_REGION]
        return app_region

    def test_files_raw_string(self):
        app_region = self._files('meow')

        self.assertEquals(1, len(app_region.files))
        self.assertEquals('meow', app_region.files[FILE_NAME])

    def test_files_raw_encoded(self):
        encoded_body = {'body': 'bWVvdw=='}
        app_region = self._files(encoded_body)

        self.assertEquals(1, len(app_region.files))
        self.assertEquals(encoded_body, app_region.files[FILE_NAME])

    def test_files_encrypted(self):
        encrypted_payload = {
            'iv': '',
            'key': '',
            'key_region': '',
            'ciphertext': '',
            'encoding': ''
        }
        app_region = self._files(encrypted_payload)

        self.assertEquals(1, len(app_region.files))
        self.assertEquals(encrypted_payload, app_region.files[FILE_NAME])

    def test_files_(self):
        app_region = self._files({})

        self.assertEquals(1, len(app_region.files))

    def _files(self, params, file_name=FILE_NAME):
        app = self.factory.app(self.orbit, {
            ALL: {
                'files': {
                    file_name: params
                }
            }
        })
        app_region = app.regions[ORBIT_REGION]
        return app_region

    def test_spot_bool(self):
        app_region = self._spot(True)
        self.assertEquals({}, app_region.spot)

    def test_spot_string(self):
        app_region = self._spot('true')
        self.assertEquals({}, app_region.spot)

    def test_spot_dict(self):
        spot_dict = {'foo': 'bar'}
        app_region = self._spot(spot_dict)
        self.assertEquals(spot_dict, app_region.spot)

    def _spot(self, params):
        app = self.factory.app(self.orbit, {
            ALL: {
                'spot': params
            }
        })
        app_region = app.regions[ORBIT_REGION]
        return app_region

    def test_public_ports_default(self):
        app = self.factory.app(self.orbit, {})
        app_region = app.regions[ORBIT_REGION]

        self.assertEqual(1, len(app_region.public_ports))
        self.assertEqual('HTTP', app_region.public_ports[80].scheme)
        self.assertEquals(('0.0.0.0/0',), app_region.public_ports[80].sources)

    def test_public_ports_custom_sources(self):
        custom_sources = ('10.0.0.0/8', '192.168.0.0/16')
        app = self.factory.app(self.orbit, {
            ALL: {
                'public_ports': {
                    80: {
                        'sources': custom_sources
                    }
                }
            }
        })
        app_region = app.regions[ORBIT_REGION]

        self.assertEqual('HTTP', app_region.public_ports[80].scheme)
        self.assertEquals(custom_sources, app_region.public_ports[80].sources)

    def test_no_elb(self):
        app = self.factory.app(self.orbit, {
            ALL: {
                'elb_availability': 'disabled'
            }
        })
        app_region = app.regions[ORBIT_REGION]

        self.assertEqual(False, app_region.load_balancer)

    def test_sample_elasticsearch(self):
        app = self._load_sample('elasticsearch.json')

        self.assertEquals('elasticsearch', app.name)
        self.assertEquals(1, len(app.regions))
        for app_region in app.regions.values():
            self.assertEquals('HTTP:9200/', app_region.health_check)

            self.assertEquals(1, len(app_region.services))
            es_service = app_region.services['elasticsearch.service']
            self.assertEquals('pwagner/elasticsearch-aws', es_service.image)
            self.assertEquals({'9200': 9200, '9300': 9300}, es_service.ports)

            self.assertEquals(1, len(app_region.volumes))
            self.assertEquals(1, len(app_region.public_ports))
            self.assertEquals(1, len(app_region.private_ports))

    def test_sample_alarms(self):
        app = self._load_sample('laika-alarms.json')
        self.assertLaika(app)
        for app_region in app.regions.values():
            self.assertEquals(3, len(app_region.alarms['endpoints']))
            self.assertEquals(4, len(app_region.alarms['triggers']))

    def test_sample_laika(self):
        app = self._load_sample('laika.json')
        self.assertLaika(app)

    def test_sample_postgres(self):
        app = self._load_sample('laika-postgres.json')

        self.assertLaika(app)
        for app_region in app.regions.values():
            self.assertEquals(1, len(app_region.databases))
            postgres = app_region.databases['postgres']
            self.assertEquals({
                'encrypted': False,
                'public': True,
                'global': 'us-east-1',
                'clients': ['0.0.0.0/0']
            }, postgres)

    def test_sample_redis(self):
        app = self._load_sample('laika-redis.json')

        self.assertLaika(app)
        for app_region in app.regions.values():
            self.assertEquals(1, len(app_region.caches))
            cache = app_region.caches['redis']
            self.assertEquals({}, cache)

    def test_sample_systemd(self):
        app = self._load_sample('laika-systemd.json')
        self.assertLaika(app, docker=False)

    def assertLaika(self, app, docker=True):
        self.assertEquals('laika', app.name)
        self.assertEquals(1, len(app.regions))
        for app_region in app.regions.values():
            self.assertEquals('HTTP:80/', app_region.health_check)

            self.assertEquals(1, len(app_region.services))
            laika_service = app_region.services['laika.service']
            if docker:
                self.assertEquals('pebbletech/spacel-laika:latest',
                                  laika_service.image)
                self.assertEquals({'80': 8080}, laika_service.ports)
            else:
                self.assertFalse(hasattr(laika_service, 'image'))

    def _load_sample(self, sample_name):
        with open('../sample/app/%s' % sample_name) as sample_in:
            sample_json = json.load(sample_in)
            return self.factory.app(self.orbit, sample_json)
