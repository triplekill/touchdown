# Copyright 2015 Isotoma Limited
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
from touchdown.core.plan import Plan
from touchdown.core import argument

from ..common import SimpleDescribe, SimpleApply, SimpleDestroy

from .key import Key


class Grant(Resource):

    resource_name = "grant"

    name = argument.String(max=8192, field="Name")
    grantee_principal = argument.String(field="GranteePrincipal")
    retiring_principal = argument.String(field="RetiringPrincipal")

    operations = argument.List(
        argument.String(choices=[
            "Decrypt",
            "Encrypt",
            "GenerateDataKey",
            "GenerateDataKeyWithoutPlaintext",
            "ReEncryptFrom",
            "ReEncryptTo",
            "CreateGrant",
            "RetireGrant",
        ]),
        field="Operations",
    )

    encryption_context = argument.Dict(field="EncryptionContextEquals")
    encryption_context_subset = argument.Dict(field="EncryptionContextSubset")

    grant_tokens = argument.List(
        argument.String(),
        field="GrantTokens",
    )

    key = argument.Resource(Key)


class Describe(SimpleDescribe, Plan):

    resource = Grant
    service_name = 'kms'
    describe_action = "list_grants"
    describe_envelope = "Grants"
    describe_filters = {}
    key = 'GrantId'

    def get_describe_filters(self):
        key = self.runner.get_plan(self.resource.key)
        if not key.resource_id:
            return None

        return {
            "KeyId": key.resource_id,
        }

    def describe_object_matches(self, grant):
        return grant['Name'] == self.resource.name


class Apply(SimpleApply, Describe):

    create_action = "create_grant"


class Destroy(SimpleDestroy, Describe):

    destroy_action = "delete_grant"
