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
from touchdown.core import argument

from ..account import AWS
from ..common import SimpleApply
from .. import serializers

# FIXME: Figure out how to bind CreateBucketConfiguration.LocationConstraint


class Bucket(Resource):

    resource_name = "bucket"

    name = argument.String(aws_field="Bucket")
    region = argument.String(default=lambda instance: instance.account.region)
    account = argument.Resource(AWS)


class Apply(SimpleApply, Target):

    resource = Bucket
    service_name = 's3'
    create_action = "create_bucket"
    describe_action = "list_buckets"
    describe_list_key = "Buckets"
    key = 'Name'

    create_serializer = serializers.Dict(
        Bucket=serializers.Argument("name"),
        CreateBucketConfiguration=serializers.Dict(
            LocationConstraint=serializers.Argument("region"),
        )
    )

    def describe_object(self):
        for bucket in self.client.list_buckets()['Buckets']:
            if bucket['Name'] == self.resource.name:
                return bucket