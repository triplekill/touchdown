# Copyright 2016 Isotoma Limited
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

from touchdown.aws.common import Resource
from touchdown.core import argument, serializers
from touchdown.core.plan import Plan

from ..account import BaseAccount
from .get_change_token import (
    GetChangeTokenApply,
    GetChangeTokenDescribe,
    GetChangeTokenDestroy,
)
from .ip_set import IPSet


class ActivatedRule(Resource):
    negated = argument.Boolean(field='Negated')


class WebACL(Resource):

    name = argument.String(field='Name')
    metric_name = argument.String(field='MetricName')
    default_action = argument.String(field='DefaultAction', choices=['BLOCK', 'ALLOW', 'COUNT'])
    activated_rules = argument.ResourceList(
        ActivatedRule,
        field='ActivatedRules',
        create=False,
    )
    account = argument.Resource(BaseAccount)


class Describe(GetChangeTokenDescribe, Plan):

    resource = WebACL
    service_name = 'waf'
    describe_action = "list_web_acls"
    describe_envelope = "WebACLSs"
    key = 'WebACLId'

    def annotate_object(self, obj):
        # Need to do a request to get the detailed information for the
        # object - we don't get this for free when doing a list.
        obj.update(self.client.get_web_acl(**{self.key: obj[self.key]})[self.describe_envelope[:-1]])
        return obj


class Apply(GetChangeTokenApply, Describe):

    create_action = "create_web_acl"

    def update_object(self):
        changes = []
        description = ["Update Web ACL"]

        for local in self.resource.predicates:
            for remote in self.object.get('Predicates', []):
                if local.matches(self.runner, remote):
                    break
            else:
                changes.append(serializers.Dict(**{
                    "Action": "INSERT",
                    "Predicate": local.serializer_with_kwargs(),
                }))
                description.append("Type => {}, Predicate={}, Action=INSERT".format(local.match_type, local.ip_set))

        for remote in self.object.get('Predicates', []):
            for local in self.resource.predicates:
                if local.matches(self.runner, remote):
                    break
            else:
                changes.append(serializers.Dict(**{
                    "Action": "DELETE",
                    "Predicate": remote,
                }))
                # TODO: consider doing a call here to a better
                # description for the deleted resource.
                description.append("Type => {}, Predicate={}, Action=DELETE".format(remote["Type"], remote["DataId"]))

        if changes:
            yield self.generic_action(
                description,
                self.client.update_web_acl,
                WebACLId=serializers.Identifier(),
                Updates=serializers.Context(serializers.Const(changes), serializers.List(serializers.SubSerializer())),
            )


class Destroy(GetChangeTokenDestroy, Describe):

    destroy_action = "delete_web_acl"

    def destroy_object(self):
        changes = []
        description = ["Delete all IPs from IP Set"]

        for remote in self.object.get('IPSetDescriptors', []):
            changes.append(serializers.Dict(**{
                "Action": "DELETE",
                "IPSetDescriptor": remote,
            }))
            description.append("Type => {}, Address={}, Action=DELETE".format(remote["Type"], remote["Value"]))

        if changes:
            yield self.generic_action(
                description,
                self.client.update_ip_set,
                IPSetId=serializers.Identifier(),
                Updates=serializers.Context(serializers.Const(changes), serializers.List(serializers.SubSerializer())),
            )

        for obj in super(Destroy, self).destroy_object():
            yield obj
