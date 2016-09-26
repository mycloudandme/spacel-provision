from spacel.provision.template.app_spot import AppSpotTemplateDecorator
from spacel.provision.template.base import BaseTemplateCache
from test import BaseSpaceAppTest, REGION


class TestAppSpotTemplateDecorator(BaseSpaceAppTest):
    def setUp(self):
        super(TestAppSpotTemplateDecorator, self).setUp()
        self.resources = {}
        self.app_spot = AppSpotTemplateDecorator()
        self.template = BaseTemplateCache().get('elb-service')

    def test_clean_up_asg(self):
        self.resources['Asg'] = {}
        self.resources['Lc'] = {}
        self.resources['AlarmScaleDown'] = {}
        outputs = {'AsgName': {'Value': {'Ref': 'Asg'}}}
        template = {
            'Resources': self.resources,
            'Outputs': outputs
        }

        self.app_spot._clean_up_asg(template)
        self.assertEquals(0, len(self.resources))
        self.assertEquals('SpotFleet', outputs['AsgName']['Value']['Ref'])

    def test_spotify_noop(self):
        self.app_spot.spotify(self.app, REGION, self.template)
        self.assertNotIn('SpotFleet', self.template['Resources'])

    def test_spotify(self):
        self.app.spot = {}

        self.app_spot.spotify(self.app, REGION, self.template)

        params = self.template['Parameters']
        resources = self.template['Resources']
        fleet_config = (resources['SpotFleet']
                        ['Properties']
                        ['SpotFleetRequestConfigData'])
        self.assertEquals('diversified', fleet_config['AllocationStrategy'])
        self.assertEquals(1, len(fleet_config['LaunchSpecifications']))
        self.assertNotIn('Asg', resources)
        self.assertNotIn('Lc', resources)
        self.assertIn('"tags":', params['UserData']['Default'])

    def test_spotify_weights(self):
        self.app.spot = {
            'weights': {
                't2.nano': 1,
                't2.micro': 2,
                't2.small': 4
            }
        }

        self.app_spot.spotify(self.app, REGION, self.template)

        fleet_config = (self.template['Resources']
                        ['SpotFleet']
                        ['Properties']
                        ['SpotFleetRequestConfigData'])
        self.assertEquals('lowestPrice', fleet_config['AllocationStrategy'])
        self.assertEquals(3, len(fleet_config['LaunchSpecifications']))
