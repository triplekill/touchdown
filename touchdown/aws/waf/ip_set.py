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


class IPSetDescriptor(Resource):

    resource_name = "ip_set_descriptor"

    address_type = argument.String(field="Type", choices=["IPV4"], default="IPV4")
    address = argument.IPNetwork(field="Value")

    @classmethod
    def clean(cls, value):
        if isinstance(value, str):
            return super(IPSetDescriptor, cls).clean({"address": value})
        return super(IPSetDescriptor, cls).clean(value)


class IpSet(Resource):

    resource_name = "ip_set"

    name = argument.String(field="Name")
    addresses = argument.ResourceList(
        IPSetDescriptor,
        field="IPSetDescriptors",
        create=False,
    )
    account = argument.Resource(BaseAccount)


class Describe(GetChangeTokenDescribe, Plan):

    resource = IpSet
    service_name = 'waf'
    describe_action = "list_ip_sets"
    describe_envelope = "IPSets"
    annotate_action = "get_ip_set"
    key = 'IPSetId'


class Apply(GetChangeTokenApply, Describe):

    create_action = "create_ip_set"

    def update_object(self):
        changes = []
        description = ["Update ip set"]

        for local in self.resource.addresses:
            for remote in self.object.get('IPSetDescriptors', []):
                if local.matches(self.runner, remote):
                    break
            else:
                changes.append(serializers.Dict(**{
                    "Action": "INSERT",
                    "IPSetDescriptor": local.serializer_with_kwargs(),
                }))
                description.append("Type => {}, Address={}, Action=INSERT".format(local.address_type, local.address))

        for remote in self.object.get('IPSetDescriptors', []):
            for local in self.resource.addresses:
                if local.matches(self.runner, remote):
                    break
            else:
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


class Destroy(GetChangeTokenDestroy, Describe):

    destroy_action = "delete_ip_set"
    container_update_action = 'update_ip_set'
    container = 'IPSetDescriptors'
    container_member = 'IPSetDescriptor'
