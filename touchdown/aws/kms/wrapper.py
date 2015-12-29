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

import tarfile
from six import StringIO

from cryptography.fernet import Fernet

from touchdown.core.plan import Plan
from touchdown.core import argument
from touchdown.interfaces import File
from ..common import SimpleDescribe

from .key import Key


class Wrapper(File):

    resource_name = "cipher"

    name = argument.String()
    file = argument.Resource(File)

    key = argument.Resource(Key)


class Describe(SimpleDescribe, Plan):

    resource = Wrapper
    service_name = 'kms'
    name = "describe"

    def get_actions(self):
        return []

    def read(self):
        kms = self.runner.get_plan(self.resource.key)
        tar = tarfile.open(
            self.runner.get_plan(self.resource.file).read(),
            "r",
        )
        f = Fernet(kms.decrypt_data_key(tar.extractfile("key").read()))
        return StringIO(f.decrypt(tar.extractfile("blob").read()))

    def write(self, c):
        kms = self.runner.get_plan(self.resource.key)
        aes_key, aes_key_protected = kms.generate_data_key()
        io = StringIO()
        tar = tarfile.open(io, 'w')

        ti = tarfile.TarInfo('key')
        ti.size = len(aes_key_protected)
        tar.addfile(ti, StringIO(aes_key_protected))

        f = Fernet(aes_key)
        encrypted = f.encrypt(c)

        ti = tarfile.TarInfo('blob')
        ti.size = len(encrypted)
        tar.addfile(ti, StringIO(encrypted))

        tar.close()

        fp = self.runner.get_plan(self.resource.file)
        fp.write(io.getvalue())
