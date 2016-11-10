from copy import deepcopy

from spacel.model.orbit import BASTION_INSTANCE_TYPE, BASTION_INSTANCE_COUNT
from spacel.provision.template.base import BaseTemplateCache


class BastionTemplate(BaseTemplateCache):
    def __init__(self, ami_finder):
        super(BastionTemplate, self).__init__(ami_finder=ami_finder)

    def bastion(self, orbit, region):
        """
        Get customized template for bastion hosts.
        :param orbit: Orbit.
        :param region: Region.
        :return: Bastion template.
        """
        bastion_count = int(orbit.get_param(region, BASTION_INSTANCE_COUNT))
        if not bastion_count:
            return False

        bastion_template = self.get('asg-bastion')

        params = bastion_template['Parameters']
        resources = bastion_template['Resources']

        # Link to VPC:
        params['VpcId']['Default'] = orbit.vpc_id(region)
        params['Orbit']['Default'] = orbit.name
        if orbit.domain:
            params['VirtualHostDomain']['Default'] = orbit.domain + '.'

        # Bastion parameters:
        bastion_type = orbit.get_param(region, BASTION_INSTANCE_TYPE)
        params['InstanceType']['Default'] = bastion_type
        params['Ami']['Default'] = self._ami.spacel_ami(region)

        params['InstanceCount']['Default'] = bastion_count
        params['InstanceCountMinusOne']['Default'] = max(bastion_count - 1, 0)

        # TODO: support multiple sources (like ELB)

        # If multiple bastions, get more EIPs:
        if bastion_count > 1:
            eip_resource = resources['ElasticIp01']
            outputs = bastion_template['Outputs']

            eip_list = (resources['Lc']
                        ['Properties']
                        ['UserData']
                        ['Fn::Base64']
                        ['Fn::Join'][1][1]
                        ['Fn::Join'][1])

            base_dns = resources['DnsRecord01']

            # Create `bastion01` record for consistency:
            eip_dns = deepcopy(base_dns)
            (eip_dns['Properties']
             ['RecordSets'][0]
             ['Name']
             ['Fn::Join'][1]).insert(0, 'bastion01')
            resources['DnsRecord01Alias'] = eip_dns

            for bastion_index in range(2, bastion_count + 1):
                eip_name = 'ElasticIp%02d' % bastion_index
                # Add resource, output:
                resources[eip_name] = eip_resource
                outputs[eip_name] = {'Value': {'Ref': eip_name}}

                # Append to `eips` list in UserData
                eip_list.append({'Fn::GetAtt': [eip_name, 'AllocationId']})

                # Add a unique DNS alias:
                eip_dns = deepcopy(base_dns)
                dns_recordset = eip_dns['Properties']['RecordSets'][0]
                dns_label = 'bastion%02d' % bastion_index
                dns_recordset['Name']['Fn::Join'][1].insert(0, dns_label)
                dns_recordset['ResourceRecords'][0]['Ref'] = eip_name
                resources['DnsRecord%02d' % bastion_index] = eip_dns

        # Expand ASG to all AZs:
        instance_subnets = orbit.public_instance_subnets(region)
        self._subnet_params(params, 'PublicInstance', instance_subnets)
        self._asg_subnets(resources, 'PublicInstance', instance_subnets)

        return bastion_template
