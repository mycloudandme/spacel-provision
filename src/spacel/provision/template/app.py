import json
import logging
import six

from spacel.aws import INSTANCE_VOLUMES
from spacel.provision import base64_encode
from spacel.provision.template.base import BaseTemplateCache

SSL_SCHEMES = ('HTTPS', 'SSL')

logger = logging.getLogger('spacel.provision.template.app')


class AppTemplate(BaseTemplateCache):
    def __init__(self, ami_finder, alarm_factory, cache_factory, rds_factory,
                 spot_decorator, acm):
        super(AppTemplate, self).__init__(ami_finder=ami_finder)
        self._alarm_factory = alarm_factory
        self._cache_factory = cache_factory
        self._rds_factory = rds_factory
        self._spot_decorator = spot_decorator
        self._acm = acm

    def app(self, app, region):
        app_template = self.get('elb-service')

        orbit = app.orbit
        params = app_template['Parameters']
        resources = app_template['Resources']

        # Link to VPC:
        params['VpcId']['Default'] = orbit.vpc_id(region)
        params['Orbit']['Default'] = orbit.name
        params['Service']['Default'] = app.name
        params['BastionSecurityGroup']['Default'] = orbit.bastion_sg(region)
        cache_subnet_group = orbit.private_cache_subnet_group(region)
        if cache_subnet_group:
            params['PrivateCacheSubnetGroup']['Default'] = cache_subnet_group
        public_rds_group = orbit.public_rds_subnet_group(region)
        if public_rds_group:
            params['PublicRdsSubnetGroup']['Default'] = public_rds_group
        private_rds_group = orbit.private_rds_subnet_group(region)
        if private_rds_group:
            params['PrivateRdsSubnetGroup']['Default'] = private_rds_group

        # Inject parameters:
        params['ElbScheme']['Default'] = app.scheme
        params['HealthCheckTarget']['Default'] = app.health_check
        params['InstanceType']['Default'] = app.instance_type
        params['InstanceMin']['Default'] = app.instance_min
        params['InstanceMax']['Default'] = app.instance_max
        params['UserData']['Default'] = self._user_data(params, app)
        params['Ami']['Default'] = self._ami.spacel_ami(region)

        if app.hostnames:
            # TODO: support multiple hostnames
            app_hostname = app.hostnames[0]
            domain = app_hostname.split('.')
            domain = '.'.join(domain[-2:]) + '.'
            params['VirtualHostDomain']['Default'] = domain
            params['VirtualHost']['Default'] = app_hostname
        else:
            params['VirtualHostDomain']['Default'] = orbit.domain + '.'
            app_hostname = '%s-%s.%s' % (app.name, orbit.name, orbit.domain)
            params['VirtualHost']['Default'] = app_hostname

        # Expand ELB to all AZs:
        public_elb_subnets = orbit.public_elb_subnets(region)
        private_elb_subnets = orbit.private_elb_subnets(region)
        self._subnet_params(params, 'PublicElb', public_elb_subnets)
        self._subnet_params(params, 'PrivateElb', private_elb_subnets)

        self._elb_subnets(resources, 'PublicElb', public_elb_subnets)
        self._elb_subnets(resources, 'PrivateElb', private_elb_subnets)

        # Expand ASG to all AZs:
        private_instance_subnets = orbit.private_instance_subnets(region)
        self._subnet_params(params, 'PrivateInstance', private_instance_subnets)
        self._asg_subnets(resources, 'PrivateInstance',
                          private_instance_subnets)

        # Public ports:
        elb_ingress = resources['ElbSg']['Properties']['SecurityGroupIngress']
        instance_ingress = resources['Sg']['Properties']['SecurityGroupIngress']
        public_elb = resources['PublicElb']['Properties']['Listeners']
        private_elb = resources['PrivateElb']['Properties']['Listeners']
        elb_ingress_ports = set()
        for port_number, port_config in app.public_ports.items():
            # Allow all sources into ELB:
            for ip_source in port_config.sources:
                elb_ingress.append({
                    'IpProtocol': 'tcp',
                    'FromPort': port_number,
                    'ToPort': port_number,
                    'CidrIp': ip_source
                })

            # Allow ELB->Instance
            internal_port = port_config.internal_port
            if internal_port not in elb_ingress_ports:
                instance_ingress.append({
                    'IpProtocol': 'tcp',
                    'FromPort': internal_port,
                    'ToPort': internal_port,
                    'SourceSecurityGroupId': {'Ref': 'ElbSg'}
                })
                elb_ingress_ports.add(internal_port)

            elb_listener = {
                'InstancePort': internal_port,
                'LoadBalancerPort': port_number,
                'Protocol': port_config.scheme,
                'InstanceProtocol': port_config.internal_scheme
            }

            if port_config.scheme in SSL_SCHEMES:
                cert = port_config.certificate
                if not cert:
                    cert = self._acm.get_certificate(region, app_hostname)
                if not cert:
                    logger.warn('Unable to find certificate for %s. ' +
                                'Specify a "certificate" or provision  in ACM.',
                                app_hostname)
                    raise Exception('Public_port %s is missing certificate.' %
                                    port_number)
                elb_listener['SSLCertificateId'] = cert

            public_elb.append(elb_listener)
            private_elb.append(elb_listener)

        # Private ports:
        for private_port, protocols in app.private_ports.items():
            port_is_string = isinstance(private_port, six.string_types)
            if port_is_string and '-' in private_port:
                from_port, to_port = private_port.split('-', 1)
                port_label = private_port.replace('-', 'to')
            else:
                from_port = private_port
                to_port = private_port
                port_label = private_port

            for protocol in protocols:
                port_resource = 'PrivatePort%s%s' % (port_label, protocol)
                resources[port_resource] = {
                    'Type': 'AWS::EC2::SecurityGroupIngress',
                    'Properties': {
                        'GroupId': {'Ref': 'Sg'},
                        'IpProtocol': protocol,
                        'FromPort': from_port,
                        'ToPort': to_port,
                        'SourceSecurityGroupId': {'Ref': 'Sg'}
                    }
                }

        # Map instance storage if available:
        instance_volumes = INSTANCE_VOLUMES.get(app.instance_type, 0)
        if instance_volumes > 0:
            block_devices = resources['Lc']['Properties']['BlockDeviceMappings']
            for volume_index in range(instance_volumes):
                device = '/dev/xvd%s' % chr((ord('b') + volume_index))
                block_devices.append({
                    'DeviceName': device,
                    'VirtualName': 'ephemeral%d' % volume_index
                })

        self._alarm_factory.add_alarms(app_template, app.alarms)
        self._cache_factory.add_caches(app, region, app_template, app.caches)
        secret_params = self._rds_factory.add_rds(app, region, app_template)

        # Order matters: SpotFleet AFTER Asg/Lc have been fully configured:
        self._spot_decorator.spotify(app, region, app_template)

        return app_template, secret_params

    @staticmethod
    def _user_data(params, app):
        user_data = ''
        if app.services:
            systemd = {}
            files = {}
            for service_name, service in app.services.items():
                unit_file = service.unit_file.encode('utf-8')
                systemd[service.name] = {
                    'body': base64_encode(unit_file)
                }
                if service.environment:
                    environment_file = '\n'.join('%s=%s' % (key, value)
                                                 for key, value in
                                                 service.environment.items())
                    files['%s.env' % service_name] = {
                        'body': base64_encode(environment_file.encode('utf-8'))
                    }
            user_data += ',"systemd":' + json.dumps(systemd)
        if app.volumes:
            params['VolumeSupport']['Default'] = 'true'
            user_data += ',"volumes":' + json.dumps(app.volumes)
        return user_data
