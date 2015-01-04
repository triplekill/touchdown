# Copyright 2014 Isotoma Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from touchdown.core.resource import Resource
from touchdown.core.target import Target
from touchdown.core.renderable import ResourceId
from touchdown.core import argument

from .vpc import VPC
from .. import serializers
from ..common import SimpleApply, hd


class Rule(Resource):

    resource_name = "rule"

    protocol = argument.String(choices=['tcp', 'udp', 'icmp'])
    from_port = argument.Integer(min=-1, max=32768)
    to_port = argument.Integer(min=-1, max=32768)
    security_groups = argument.ResourceList("touchdown.aws.vpc.security_group.SecurityGroup")
    networks = argument.List()


class SecurityGroup(Resource):

    resource_name = "security_group"

    name = argument.String(aws_field="GroupName")
    description = argument.String(aws_field="Description")
    vpc = argument.Resource(VPC, aws_field="VpcId")
    ingress = argument.ResourceList(Rule)
    egress = argument.ResourceList(Rule)
    tags = argument.Dict()


class Apply(SimpleApply, Target):

    resource = SecurityGroup
    service_name = 'ec2'
    create_action = "create_security_group"
    describe_action = "describe_security_groups"
    describe_list_key = "SecurityGroups"
    key = 'SecurityGroupId'

    IPPermissionList = serializers.List(serializers.Dict(
        IPProtocol=serializers.Argument("protocol"),
        FromPort=serializers.Argument("from_port"),
        ToPort=serializers.Argument("to_port"),
        UserIdGroupPairs=serializers.List(serializers.Dict(
            UserId=serializers.Property("OwnerId"),
            GroupId=serializers.Identifier(),
        ), inner=serializers.Argument("security_groups"), skip_empty=True),
        IpRanges=serializers.List(serializers.Dict(
            CidrIp=serializers.String(),
        ), inner=serializers.Argument("networks"), skip_empty=True)
    ))

    def get_describe_filters(self):
        vpc = self.runner.get_target(self.resource.vpc)
        return {
            "Filters": [
                {'Name': 'group-name', 'Values': [self.resource.name]},
                {'Name': 'vpc-id', 'Values': [vpc.resource_id or '']}
            ],
        }

    def update_object(self):
        remote_rules = frozenset([hd(d) for d in self.object.get("IpPermissions", [])])
        local_rules = frozenset(self.IPPermissionList.render(self.runner, self.resource.ingress))
        for rule in (local_rules - remote_rules):
            yield self.generic_action(
                "Authorize ingress for port {} to {}".format(rule['FromPort'], rule['ToPort']),
                self.client.authorize_security_group_ingress,
                GroupId=ResourceId(self.resource),
                #FIXME
            )

        for rule in (remote_rules - local_rules):
            yield self.generic_action(
                "Deauthorize ingress for port {} to {}".format(rule['FromPort'], rule['ToPort']),
                self.client.authorize_security_group_ingress,
                GroupId=ResourceId(self.resource),
                #FIXME
            )

        remote_rules = frozenset(self.object.get("IpPermissionsEgress", []))
        local_rules = frozenset(self.IPPermissionList.render(self.runner, self.resource.egress))
        for rule in (local_rules - remote_rules):
            yield self.generic_action(
                "Authorize egress for port {} to {}".format(rule['FromPort'], rule['ToPort']),
                self.client.authorize_security_group_egress,
                GroupId=ResourceId(self.resource),
                #FIXME
            )

        for rule in (remote_rules - local_rules):
            yield self.generic_action(
                "Deauthorize egress for port {} to {}".format(rule['FromPort'], rule['ToPort']),
                self.client.authorize_security_group_egress,
                GroupId=ResourceId(self.resource),
                #FIXME
            )