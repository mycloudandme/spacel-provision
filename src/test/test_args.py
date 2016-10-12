from mock import MagicMock, call, patch
import unittest
from six import BytesIO
from six.moves.urllib.error import HTTPError
from six.moves.urllib.parse import urlparse

from spacel.args import parse_args, parse_s3

HTTP_ORBIT = 'http://test.com/orbit'
HTTP_APP = 'https://test.com/app'

FILE_ORBIT = 'test/args/orbit'
FILE_APP = 'test/args/app'


class TestArgParse(unittest.TestCase):
    def test_parse_args_no_args(self):
        orbit, app = parse_args([], BytesIO())
        self.assertIsNone(orbit)
        self.assertIsNone(app)

    def test_parse_args_stdin(self):
        orbit, app = parse_args(['-', '-'], BytesIO(
            '{"foo":"bar"}{"foz":"baz"}'.encode('utf-8')
        ))
        self.assertEquals({'foo': 'bar'}, orbit)
        self.assertEquals({'foz': 'baz'}, app)

    def test_parse_args_no_stdin(self):
        tty_in = MagicMock()
        tty_in.isatty.return_value = True

        orbit, app = parse_args(['-', '-'], tty_in)

        self.assertIsNone(orbit)
        self.assertIsNone(app)

    @patch('spacel.args.urlopen')
    def test_read_manifest_http(self, mock_urlopen):
        mock_urlopen.side_effect = [
            BytesIO('{"foo":"bar"}'.encode('utf-8')),
            BytesIO('{"foz":"baz"}'.encode('utf-8'))
        ]

        orbit, app = parse_args([HTTP_ORBIT, HTTP_APP], BytesIO())

        self.assertEquals({'foo': 'bar'}, orbit)
        self.assertEquals({'foz': 'baz'}, app)
        mock_urlopen.assert_has_calls([
            call(HTTP_ORBIT),
            call(HTTP_APP)
        ])

    def test_read_manifest_file(self):
        orbit, app = parse_args([FILE_ORBIT, FILE_APP], BytesIO())

        self.assertEquals({'foo': 'bar'}, orbit)
        self.assertEquals({'foz': 'baz'}, app)

    @patch('spacel.args.urlopen')
    def test_read_manifest_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = HTTPError(HTTP_ORBIT, 404, 'Kaboom', {},
                                             None)

        orbit, app = parse_args([HTTP_ORBIT, HTTP_APP], BytesIO())

        self.assertIsNone(orbit)
        self.assertIsNone(app)

    @patch('spacel.args.parse_s3')
    @patch('spacel.args.boto3')
    def test_read_manifest_s3(self, mock_boto, mock_parse_s3):
        s3_resource = MagicMock()
        s3_resource.Object.return_value.get.side_effect = [
            {'Body': BytesIO('{"foo": "bar"}'.encode('utf-8'))},
            {'Body': BytesIO('{"foz": "baz"}'.encode('utf-8'))}
        ]

        mock_boto.resource.return_value = s3_resource
        mock_parse_s3.return_value = ('us-west-2', 2, 3)

        orbit, app = parse_args(['s3://bucket/key.txt', 's3://bucket/key.txt'],
                                BytesIO())

        self.assertEquals({'foo': 'bar'}, orbit)
        self.assertEquals({'foz': 'baz'}, app)
        mock_boto.resource.assert_called_with('s3', 'us-west-2')

    def test_read_manifest_not_supported(self):
        orbit, app = parse_args(['magnet:?', 'magnet:?'], BytesIO())
        self.assertIsNone(orbit)
        self.assertIsNone(app)

    def test_parse_s3_bucket_only(self):
        region, bucket, key = self._s3_parse('s3://bucket/key.txt')

        self.assertEquals('us-east-1', region)
        self.assertEquals('bucket', bucket)
        self.assertEquals('key.txt', key)

    def test_parse_s3_region_bucket_in_path(self):
        region, bucket, key = self._s3_parse(
            's3://s3-us-west-2.amazonaws.com/bucket/key.txt')

        self.assertEquals('us-west-2', region)
        self.assertEquals('bucket', bucket)
        self.assertEquals('key.txt', key)

    def test_parse_s3_region_bucket_in_host(self):
        region, bucket, key = self._s3_parse(
            's3://bucket.s3.us-west-2.amazonaws.com/key.txt')

        self.assertEquals('us-west-2', region)
        self.assertEquals('bucket', bucket)
        self.assertEquals('key.txt', key)

    @staticmethod
    def _s3_parse(u):
        return parse_s3(urlparse(u))
