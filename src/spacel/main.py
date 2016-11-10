import logging
import os
import sys

from colorlog import ColoredFormatter
from spacel.aws import AmiFinder, ClientCache
from spacel.args import parse_args
from spacel.model import SpaceApp, Orbit
from spacel.provision import (ChangeSetEstimator, CloudProvisioner,
                              LambdaUploader, ProviderOrbitFactory,
                              TemplateUploader)

from spacel.provision.template import (AppTemplate, AppSpotTemplateDecorator,
                                       BastionTemplate, IngressResourceFactory,
                                       TablesTemplate, VpcTemplate)
from spacel.provision.alarm import AlarmFactory
from spacel.provision.db import CacheFactory, RdsFactory
from spacel.security import (AcmCertificates, KmsCrypto, KmsKeyFactory,
                             PasswordManager)


def main(args, in_stream):
    orbit_json, app_json = parse_args(args, in_stream)
    if not orbit_json or not app_json:
        return -1

    orbit = Orbit(orbit_json)
    app = SpaceApp(orbit, app_json)

    return provision(app)


def provision(app):
    clients = ClientCache()
    # Lambda function storage
    lambda_bucket = os.environ.get('LAMBDA_BUCKET')
    lambda_region = os.environ.get('LAMBDA_REGION', 'us-west-2')
    lambda_up = LambdaUploader(clients, lambda_region, lambda_bucket)
    # CloudFormation template storage
    template_bucket = os.environ.get('TEMPLATE_BUCKET', lambda_bucket)
    template_region = os.environ.get('TEMPLATE_REGION', lambda_region)
    template_up = TemplateUploader(clients, template_region, template_bucket)
    pagerduty_default = os.environ.get('WEBHOOKS_PAGERDUTY')
    pagerduty_api_key = os.environ.get('PAGERDUTY_API_KEY')
    alarm_factory = AlarmFactory.get(pagerduty_default,
                                     pagerduty_api_key,
                                     lambda_up)
    ingress_factory = IngressResourceFactory(clients)
    kms_key_factory = KmsKeyFactory(clients)
    kms_crypto = KmsCrypto(clients, kms_key_factory)
    password_manager = PasswordManager(clients, kms_crypto)
    cache_factory = CacheFactory(ingress_factory)
    rds_factory = RdsFactory(clients, ingress_factory, password_manager)
    # Templates:
    ami_finder = AmiFinder()
    app_spot = AppSpotTemplateDecorator()
    acm = AcmCertificates(clients)
    app_template = AppTemplate(ami_finder, alarm_factory, cache_factory,
                               rds_factory, app_spot, acm)
    bastion_template = BastionTemplate(ami_finder)
    tables_template = TablesTemplate()
    vpc_template = VpcTemplate()
    change_sets = ChangeSetEstimator()
    orbit_factory = ProviderOrbitFactory.get(clients, change_sets, template_up,
                                             vpc_template,
                                             bastion_template,
                                             tables_template)
    orbit_factory.get_orbit(app.orbit)
    provisioner = CloudProvisioner(clients, change_sets, template_up,
                                   app_template)
    provisioner.app(app)
    return 0


if __name__ == '__main__':  # pragma: no cover
    formatter = ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        reset=True,
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red'
        }
    )
    stream_out = logging.StreamHandler()
    stream_out.setLevel(logging.DEBUG)
    stream_out.setFormatter(formatter)
    logging.getLogger().addHandler(stream_out)
    logging.getLogger('boto3').setLevel(logging.CRITICAL)
    logging.getLogger('botocore').setLevel(logging.CRITICAL)
    logging.getLogger('spacel').setLevel(logging.DEBUG)

    result = main(sys.argv[1:], sys.stdin)
    sys.exit(result)
