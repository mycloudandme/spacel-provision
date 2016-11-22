import logging

logger = logging.getLogger('spacel.model.app')

ON_PUBLIC_SUBNET = {
    'multi-region',
    'internet-facing'
}

INSTANCE_AVAILABILITY = ON_PUBLIC_SUBNET | {
    'private',
}

ELB_AVAILABILITY = INSTANCE_AVAILABILITY | {
    'disabled',
}

UPDATE_POLICY = {
    'rolling',
    'redblack',
    'disabled'
}


class SpaceApp(object):
    """
    Configuration of a hosted application.
    Contains SpaceAppRegion entries for each configured region.
    """

    def __init__(self, orbit, name, regions=None, **kwargs):
        self.orbit = orbit
        self.name = name

        if regions:
            self.regions = {}
            for region in regions:
                orbit_region = orbit.regions.get(region)
                if orbit_region:
                    self.regions[region] = SpaceAppRegion(self, orbit_region,
                                                          **kwargs)
                    continue

                logger.warn(
                    'App "%s" has invalid region "%s". Valid regions: %s',
                    name, region, ', '.join(orbit.regions))
        else:
            self.regions = {region: SpaceAppRegion(self, orbit_region, **kwargs)
                            for region, orbit_region in orbit.regions.items()}

    @property
    def valid(self):
        if not self.name:
            logger.error('Application has no "name".')
            return False

        valid = True
        if not self.regions:
            logger.error('Application "%s" has no valid "regions".', self.name)
            valid = False

        for region, app_region in self.regions.items():
            if not app_region.valid:
                logger.error('Application "%s" has valid regions: "%s".',
                             self.name, region)
                valid = False
        return valid

    @property
    def full_name(self):
        return '%s-%s' % (self.orbit.name, self.name)


class SpaceAppRegion(object):
    def __init__(self,
                 app,
                 orbit_region,
                 elastic_ips=False,
                 elb_availability='internet-facing',
                 health_check='TCP:80',
                 hostnames=(),
                 instance_availability='private',
                 instance_max=2,
                 instance_min=1,
                 instance_type='t2.nano',
                 local_health_check='TCP:80',
                 update_policy='rolling',
                 spot=None):
        self.app = app
        self.orbit_region = orbit_region
        self.region = orbit_region.region
        self.elastic_ips = elastic_ips
        self.elb_availability = elb_availability
        self.health_check = health_check
        self.hostnames = hostnames
        self.instance_availability = instance_availability
        self.instance_max = instance_max
        self.instance_min = instance_min
        self.instance_type = instance_type
        self.local_health_check = local_health_check
        self.update_policy = update_policy
        self.spot = spot
        self.alarms = {}
        self.caches = {}
        self.databases = {}
        self.files = {}
        self.private_ports = {}
        self.public_ports = {}
        self.services = {}
        self.volumes = {}

        self.alarm_endpoints = {}

    @property
    def load_balancer(self):
        """Does app use load balancer?"""
        return self.elb_availability != 'disabled'

    @property
    def elb_public(self):
        return self.elb_availability in ON_PUBLIC_SUBNET

    @property
    def instance_public(self):
        return self.instance_availability in ON_PUBLIC_SUBNET

    @property
    def valid(self):
        valid = True
        if self.elb_availability not in ELB_AVAILABILITY:
            self._invalid_value('elb_availability', self.elb_availability,
                                ELB_AVAILABILITY)
            valid = False
        if self.instance_availability not in INSTANCE_AVAILABILITY:
            self._invalid_value('instance_availability',
                                self.instance_availability,
                                INSTANCE_AVAILABILITY)
            valid = False
        if self.update_policy not in UPDATE_POLICY:
            self._invalid_value('update_policy', self.update_policy,
                                UPDATE_POLICY)
            valid = False
        return valid

    def _invalid_value(self, key, value, values):
        logger.error('Application "%s" has invalid "%s": "%s". Valid: %s',
                     self.app.name, key, value,
                     ', '.join('"%s"' % v for v in values))


class SpaceServicePort(object):
    def __init__(self,
                 port,
                 certificate=None,
                 internal_port=None,
                 internal_scheme=None,
                 scheme=None,
                 sources=('0.0.0.0/0',)
                 ):
        self.certificate = certificate
        internal_port = internal_port or port
        self.internal_port = internal_port
        self.internal_scheme = internal_scheme or self._scheme(internal_port)
        self.scheme = scheme or self._scheme(port)
        self.sources = sources

    @staticmethod
    def _scheme(port):
        if str(port) == '443':
            return 'HTTPS'
        return 'HTTP'
