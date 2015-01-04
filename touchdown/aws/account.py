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

from botocore import session

from touchdown.core.resource import Resource
from touchdown.core.target import Target
from touchdown.core import argument

from touchdown.core.workspace import Workspace


class AWS(Resource):

    resource_name = "aws"

    region = argument.String()
    access_key_id = argument.String()
    secret_access_key = argument.String()
    root = argument.Resource(Workspace)


class Info(Target):

    resource = AWS
    default = True
    name = "info"
    _session = None

    @property
    def session(self):
        if not self._session:
            self._session = session.get_session()
            self._session.access_key_id = self.resource.access_key_id or None
            self._session.secret_access_key = self.resource.secret_access_key or None
            self._session.region = self.resource.region
        return self._session