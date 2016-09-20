import unittest
import json
from mock import MagicMock
from spacel.model import SpaceApp
from spacel.provision.db.rds import RdsFactory
from spacel.provision.template import IngressResourceFactory
from spacel.security import EncryptedPayload, PasswordManager

DB_NAME = 'test-db'
REGION = 'us-west-2'


class TestRdsFactory(unittest.TestCase):
    def setUp(self):
        self.user_data_params = [
            '{',
            '\"databases\":{',
            '} }'
        ]
        self.resources = {
            'Lc': {
                'Properties': {
                    'UserData': {
                        'Fn::Base64': {
                            'Fn::Join': [
                                '', self.user_data_params
                            ]
                        }
                    }
                }
            }
        }
        self.parameters = {}
        self.template = {
            'Parameters': self.parameters,
            'Resources': self.resources
        }
        self.db_params = {}

        self.app = MagicMock(spec=SpaceApp)
        self.app.name = 'test-app'
        self.app.orbit = MagicMock()
        self.app.orbit.name = 'test-orbit'
        self.app.databases = {
            DB_NAME: self.db_params
        }

        self.ingress = MagicMock(spec=IngressResourceFactory)
        self.password_manager = MagicMock(spec=PasswordManager)
        self.password_manager.get_password.return_value = EncryptedPayload(
            b'1234567890123456',
            b'1234567890123456',
            b'1234567890123456',
            'us-east-1',
            'utf-8'
        ), lambda: 'test-password'
        self.rds_factory = RdsFactory(self.ingress, self.password_manager)

    def test_add_rds(self):
        self.rds_factory.add_rds(self.app, REGION, self.template)
        self.assertEquals(3, len(self.resources))

        # Resolve {'Ref':}s to a string:
        user_data_params = normalize(self.user_data_params)
        user_data = json.loads(''.join(user_data_params))
        db_user_data = user_data['databases'][DB_NAME]
        self.assertEquals('Dbtestdb', db_user_data['name'])


def normalize(cf_json):
    if isinstance(cf_json, dict):
        ref = cf_json.get('Ref')
        if ref is not None:
            return ref
        normalized = {}
        for key, value in cf_json.items():
            normalized[key] = normalize(value)
        return normalized
    if isinstance(cf_json, list):
        return [normalize(f) for f in cf_json]

    return cf_json