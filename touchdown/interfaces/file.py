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

import os
import subprocess
import tempfile

from touchdown.core.resource import Resource
from touchdown.core.plan import Plan
from touchdown.core import errors


class FileNotFound(errors.Error):
    pass


class File(Resource):
    pass


class Edit(Plan):

    resource = File
    name = "edit"

    def get_editor(self):
        for var in ("VISUAL", "EDITOR"):
            if var in os.environ:
                return os.environ[var]

        # if is_windows():
        #     return "notepad.exe"

        for editor in ("vim", "nano"):
            for path in os.environ.get("PATH", "/usr/bin").split(os.path.pathsep):
                e = os.path.join(path, editor)
                if os.path.exists(e):
                    return e

    def edit_file(self, filename):
        editor = self.get_editor()

        try:
            p = subprocess.Popen([editor, filename])
            exit_code = p.wait()
        except OSError as e:
            raise errors.Error('Editing failed: %s' % (e))

        if exit_code != 0:
            raise errors.Error('Editing failed: Exit code' % exit_code)

    def edit(self, contents):
        contents = contents or ''
        if contents and not contents.endswith('\n'):
            contents += '\n'

        fd, name = tempfile.mkstemp(prefix='edit-')
        try:
            f = os.fdopen(fd, 'wb')
            f.write(contents)
            f.close()
            timestamp = os.path.getmtime(name)

            self.edit_file(name)

            changed = os.path.getmtime(name) != timestamp

            with open(name, 'rb') as fp:
                contents = fp.read()

            return contents, changed
        finally:
            os.unlink(name)

    def execute(self):
        f = self.runner.get_service(self.resource, "describe")
        contents, changed = self.edit(f.read().read())
        if changed:
            f.write(contents)
