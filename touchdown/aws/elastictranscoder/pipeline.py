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
from ..common import SimpleDescribe, SimpleApply, SimpleDestroy

from ..s3 import Bucket
from ..iam import Role


class Pipeline(Resource):

    resource_name = "pipeline"

    name = argument.String(aws_field="Name")
    input_bucket = argument.Resource(Bucket, aws_field="InputBucket")
    output_bucket = argument.Resource(Bucket, aws_field="OutputBucket")
    role = argument.Resource(Role, aws_field="Role")
    # key = argument.Resource(KmsKey, aws_field="AwsKmsKeyArn")
    # notifications = argument.Resource(Topic, aws_field="Notifications")
    content_config = argument.Dict(aws_field="ContentConfig")
    thumbnail_config = argument.Dict(aws_field="ThumbnailConfig")
    account = argument.Resource(AWS)


class Describe(SimpleDescribe, Target):

    resource = Pipeline
    service_name = 'elastictranscoder'
    describe_action = "list_pipelines"
    describe_list_key = "Pipelines"
    key = 'Id'

    def describe_object(self):
        for pipeline in self.client.list_buckets()['Pipelines']:
            if pipeline['Name'] == self.resource.name:
                return pipeline


class Apply(SimpleApply, Target):

    create_action = "create_pipeline"
    update_action = "update_pipeline"


class Destroy(SimpleDestroy, Target):

    destroy_action = "delete_pipeline"
