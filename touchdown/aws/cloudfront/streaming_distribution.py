# Copyright 2014-2015 Isotoma Limited
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

import uuid

from touchdown.core.resource import Resource
from touchdown.core.plan import Plan
from touchdown.core import argument, serializers

from ..account import Account
from ..common import SimpleDescribe, SimpleApply, SimpleDestroy

from ..s3 import Bucket

from .common import S3Origin, CloudFrontList


class StreamingLoggingConfig(Resource):

    resource_name = "streaming_logging_config"
    dot_ignore = True

    enabled = argument.Boolean(field="Enabled", default=False)
    bucket = argument.Resource(Bucket, field="Bucket", serializer=serializers.Default(default=None), default="")
    prefix = argument.String(field="Prefix", default="")


class StreamingDistribution(Resource):

    resource_name = "streaming_distribution"

    extra_serializers = {
        "CallerReference": serializers.Expression(
            lambda runner, object: runner.get_plan(object).object.get('StreamingDistributionConfig', {}).get('CallerReference', str(uuid.uuid4()))
        ),
        "Aliases": CloudFrontList(serializers.Chain(
            serializers.Context(serializers.Argument("name"), serializers.ListOfOne()),
            serializers.Context(serializers.Argument("aliases"), serializers.List()),
        )),
    }

    name = argument.String()
    comment = argument.String(field='Comment', default=lambda instance: instance.name)
    aliases = argument.List()
    enabled = argument.Boolean(default=True, field="Enabled")
    origin = argument.Resource(
        S3Origin,
        field="S3Origin",
        serializer=serializers.Resource(),
    )
    logging = argument.Resource(
        StreamingLoggingConfig,
        default=lambda instance: dict(enabled=False),
        field="Logging",
        serializer=serializers.Resource(),
    )
    price_class = argument.String(
        default="PriceClass_100",
        choices=['PriceClass_100', 'PriceClass_200', 'PriceClass_All'],
        field="PriceClass",
    )

    account = argument.Resource(Account)


class Describe(SimpleDescribe, Plan):

    resource = StreamingDistribution
    service_name = 'cloudfront'
    describe_filters = {}
    describe_action = "list_streaming_distributions"
    describe_envelope = 'StreamingDistributionList.Items'
    key = 'Id'

    def get_describe_filters(self):
        return {"Id": self.object['Id']}

    def describe_object_matches(self, d):
        return self.resource.name in d['Aliases'].get('Items', [])

    def describe_object(self):
        distribution = super(Describe, self).describe_object()
        if distribution:
            result = self.client.get_streaming_distribution(Id=distribution['Id'])
            distribution = {"ETag": result["ETag"], "Id": distribution["Id"]}
            distribution.update(result['StreamingDistribution'])
            return distribution


class Apply(SimpleApply, Describe):

    create_action = "create_streaming_distribution"
    create_response = "not-that-useful"
    waiter = "streaming_distribution_deployed"

    def get_create_serializer(self):
        return serializers.Dict(
            DistributionConfig=serializers.Resource(),
        )


class Destroy(SimpleDestroy, Describe):

    destroy_action = "delete_streaming_distribution"

    def get_destroy_serializer(self):
        return serializers.Dict(
            Id=self.resource_id,
            IfMatch=self.object['ETag'],
        )

    def destroy_object(self):
        if not self.object:
            return

        if self.object['StreamingDistributionConfig'].get('Enabled', False):
            yield self.generic_action(
                "Disable streaming distribution",
                self.client.update_streaming_distribution,
                Id=self.object['Id'],
                IfMatch=self.object['ETag'],
                DistributionConfig=serializers.Resource(
                    Enabled=False,
                ),
            )

            yield self.get_waiter(
                ["Waiting for streaming distribution to enter disabled state"],
                "streaming_distribution_deployed",
            )

        for change in super(Destroy, self).destroy_object():
            yield change