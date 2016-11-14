import unittest

from mock import MagicMock

from spacel.aws import ClientCache
from spacel.model import Orbit, SpaceApp
from spacel.provision.app.space import SpaceElevatorAppFactory
from spacel.provision.changesets import ChangeSetEstimator
from spacel.provision.s3 import TemplateUploader
from spacel.provision.template import AppTemplate

REGIONS = ('us-east-1', 'us-west-2')


class TestSpaceElevatorAppFactory(unittest.TestCase):
    def setUp(self):
        self.clients = MagicMock(spec=ClientCache)
        self.change_sets = MagicMock(spec=ChangeSetEstimator)
        self.templates = MagicMock(spec=TemplateUploader)
        self.app_template = MagicMock(spec=AppTemplate)
        self.app_template.app.return_value = {'Spacel': 'Rules'}, {}

        self.provisioner = SpaceElevatorAppFactory(self.clients,
                                                   self.change_sets,
                                                   self.templates,
                                                   self.app_template)
        self.provisioner._wait_for_updates = MagicMock()
        self.provisioner._stack = MagicMock()
        self.provisioner._delete_stack = MagicMock()

        self.orbit = Orbit({
            'regions': REGIONS
        })
        self.app = SpaceApp(self.orbit, {})

    def test_app_create(self):
        self.provisioner._stack.return_value = 'create'
        self.provisioner.app(self.app)

        self.assertEquals(len(REGIONS), self.provisioner._stack.call_count)
        self.assertEquals(1, self.provisioner._wait_for_updates.call_count)

    def test_app_delete(self):
        self.provisioner._stack.return_value = 'delete'
        self.provisioner.delete_app(self.app)

        self.assertEquals(len(REGIONS),
                          self.provisioner._delete_stack.call_count)
        self.assertEquals(1, self.provisioner._wait_for_updates.call_count)

    def test_app_syntax_rejected(self):
        self.app_template.app.return_value = False, False
        self.provisioner.app(self.app)

        self.provisioner._stack.assert_not_called()
        self.assertEquals(1, self.provisioner._wait_for_updates.call_count)
