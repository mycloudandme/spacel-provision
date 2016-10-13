from io import BytesIO
from mock import MagicMock, patch, ANY
from six.moves.urllib.error import HTTPError

from spacel.provision.alarm.endpoint.pagerduty import (PagerDutyEndpoints,
                                                       INTEGRATION_TYPE)
from test.provision.alarm.endpoint import RESOURCE_NAME, BaseEndpointTest

DEFAULT_URL = 'https://api.pagerduty.com/hook'
OTHER_URL = 'https://test.com'

SERVICE_ID = '123456'
SERVICE_NAME = 'test-service'
API_KEY = 'api-key'

INTEGRATION_KEY = '123456789012345667890'
INTEGRATION_KEY_URL = 'https://events.pagerduty.com/adapter' \
                      '/cloudwatch_sns/v1//123456789012345667890'


class TestPagerDutyEndpoints(BaseEndpointTest):
    def setUp(self):
        super(TestPagerDutyEndpoints, self).setUp()
        self.endpoint = PagerDutyEndpoints(DEFAULT_URL, API_KEY)
        self.template['Parameters'] = {
            'Orbit': {
                'Default': 'test'
            },
            'Service': {
                'Default': 'test-app'
            }
        }

    def topic_resource(self):
        return 'EndpointPagerDutyTestResourceTopic'

    def test_add_endpoints_invalid(self):
        self.endpoint = PagerDutyEndpoints(None, None)
        actions = self.endpoint.add_endpoints(self.template, RESOURCE_NAME, {})
        self.assertEquals(0, len(actions))
        self.assertEquals(0, len(self.resources))

    def test_add_endpoints(self):
        actions = self.endpoint.add_endpoints(self.template, RESOURCE_NAME, {})
        self.assertNotEquals(0, len(actions))
        self.assertEquals(1, len(self.resources))
        self.assertIn(self.topic_resource(), self.resources)
        self.assertEquals(1, len(self.subscriptions()))

    def test_get_url_simple(self):
        url = self.endpoint._get_url(self.template, {
            'url': OTHER_URL
        })
        self.assertEquals(OTHER_URL, url)

    def test_get_url_no_headers(self):
        self.endpoint._integration_key = MagicMock()
        self.endpoint._service_id = MagicMock()
        self.endpoint._pd_headers = {}

        url = self.endpoint._get_url(self.template, {})
        self.assertEquals(DEFAULT_URL, url)

        # No API keys? No API calls:
        self.endpoint._integration_key.assert_not_called()
        self.endpoint._service_id.assert_not_called()

    def test_get_url_service_id(self):
        self.endpoint._integration_key = MagicMock(return_value=INTEGRATION_KEY)
        self.endpoint._service_id = MagicMock()

        url = self.endpoint._get_url(self.template, {
            'service': SERVICE_ID
        })

        self.assertEquals(INTEGRATION_KEY_URL, url)

        self.endpoint._integration_key.assert_called_with(SERVICE_ID)
        self.endpoint._service_id.assert_not_called()

    def test_get_url_escalation_success(self):
        # Lookup by escalation policy finds service, which has integration key:
        self.endpoint._integration_key = MagicMock(return_value=INTEGRATION_KEY)
        self.endpoint._service_id = MagicMock(return_value=SERVICE_ID)
        self.endpoint._pd_api = MagicMock(return_value={
            'escalation_policy': {
                'summary': 'Test Policy'
            }
        })

        url = self.endpoint._get_url(self.template, {
            'escalation_policy': '654321'
        })

        self.assertEquals(INTEGRATION_KEY_URL, url)

    def test_get_url_escalation_missing(self):
        # Lookup by escalation policy, policy not found:
        self.endpoint._integration_key = MagicMock(return_value=INTEGRATION_KEY)
        self.endpoint._service_id = MagicMock(return_value=SERVICE_ID)
        self.endpoint._pd_api = MagicMock(return_value=None)

        url = self.endpoint._get_url(self.template, {
            'escalation_policy': '654321'
        })

        self.assertEquals(DEFAULT_URL, url)

    def test_integration_key_missing(self):
        """Look up integration key, service not found."""
        self.endpoint._pd_api = MagicMock(return_value=None)

        integration_key = self.endpoint._integration_key(SERVICE_ID)
        self.assertIsNone(integration_key)

    def test_integration_key_existing(self):
        """Look up integration key, discover existing integration."""
        self.endpoint._pd_api = MagicMock()
        self.endpoint._pd_api.side_effect = [
            {
                'service': {
                    'integrations': [{
                        'id': '123456',
                        'type': INTEGRATION_TYPE
                    }]
                }
            },
            {
                'integration': {
                    'id': '123456',
                    'integration_key': INTEGRATION_KEY
                }
            }
        ]

        integration_key = self.endpoint._integration_key(SERVICE_ID)
        self.assertEquals(INTEGRATION_KEY, integration_key)

    def test_integration_key_create(self):
        """Look up integration key, create new integration."""
        self.endpoint._pd_api = MagicMock()
        self.endpoint._pd_api.side_effect = [
            {
                'service': {
                    'integrations': []
                }
            },
            {
                'integration': {
                    'id': '123456',
                    'integration_key': INTEGRATION_KEY
                }
            }
        ]

        integration_key = self.endpoint._integration_key(SERVICE_ID)
        self.assertEquals(INTEGRATION_KEY, integration_key)

    def test_service_id_existing(self):
        """Look up service id, discover existing."""
        service_id = self.endpoint._service_id({
            'services': [{
                'summary': SERVICE_NAME,
                'self': 'http://test/' + SERVICE_ID}
            ]},
            '', SERVICE_NAME)
        self.assertEquals(SERVICE_ID, service_id)

    def test_service_id_create(self):
        """Look up service id, create."""
        self.endpoint._pd_api = MagicMock(return_value={
            'service': {
                'id': SERVICE_ID
            }
        })
        service_id = self.endpoint._service_id({}, '', SERVICE_NAME)
        self.assertEquals(SERVICE_ID, service_id)

    def test_service_id_create_failed(self):
        """Look up service id, create."""
        self.endpoint._pd_api = MagicMock(return_value=None)
        service_id = self.endpoint._service_id({}, '', SERVICE_NAME)
        self.assertIsNone(service_id)

    @patch('spacel.provision.alarm.endpoint.pagerduty.urlopen')
    def test_pd_api_missing(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError('/', 404, 'Not Found', None,
                                             BytesIO(b'{}'))

        response = self.endpoint._pd_api('/test')

        self.assertIsNone(response)

    @patch('spacel.provision.alarm.endpoint.pagerduty.urlopen')
    def test_pd_api_exception(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError('/', 500, 'Kaboom', None,
                                             BytesIO(b'{}'))

        self.assertRaises(HTTPError, self.endpoint._pd_api, '/test')

    @patch('spacel.provision.alarm.endpoint.pagerduty.urlopen')
    def test_pd_api_post_data(self, mock_urlopen):
        self._mock_response(mock_urlopen)

        response = self.endpoint._pd_api('/test', data={}, method='POST')

        mock_urlopen.assert_called_with(ANY)
        self.assertEquals({'foo': 'bar'}, response)

    @patch('spacel.provision.alarm.endpoint.pagerduty.urlopen')
    def test_pd_api(self, mock_urlopen):
        self._mock_response(mock_urlopen)

        response = self.endpoint._pd_api('/test')

        mock_urlopen.assert_called_with(ANY)
        self.assertEquals({'foo': 'bar'}, response)

    @staticmethod
    def _mock_response(mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = '{"foo":"bar"}'.encode('utf-8')
        mock_urlopen.return_value = mock_response

    def test_get_param_default(self):
        parameters = {
            'Foo': {'Default': 'foo'}
        }
        self.assertEquals('foo', self.endpoint._get_param_default(parameters,
                                                                  'Foo'))

        self.assertEquals('foo', self.endpoint._get_param_default(parameters,
                                                                  'Bar',
                                                                  'Foo',
                                                                  'Baz'))
        self.assertEquals(None, self.endpoint._get_param_default({}))
