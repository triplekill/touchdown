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

from six.moves import configparser

from touchdown.core.action import Action
from touchdown.core.plan import Plan
from touchdown.core import argument, errors, resource, serializers

from . import IniFile


class Variable(resource.Resource):

    resource_name = "variable"

    name = argument.String()
    retain_default = argument.Boolean(default=False)
    config = argument.Resource(IniFile)


class Describe(Plan):

    resource = Variable
    name = "describe"

    def get_actions(self):
        val, user_set = self.runner.get_service(self.resource, "get").execute()
        self.object = {
            "Value": val,
            "UserSet": user_set,
        }
        return []


class ApplyAction(Action):

    @property
    def description(self):
        yield "Generate and store setting {!r}".format(self.resource.name)

    def run(self):
        default = serializers.maybe(self.resource.default).render(
            self.runner, self.resource
        )
        self.runner.get_service(self.resource, "set").execute(default)


class Apply(Plan):

    resource = Variable
    name = "apply"

    def get_actions(self):
        val, user_set = self.runner.get_service(self.resource, "get").execute()
        if not user_set and self.resource.retain_default:
            yield ApplyAction(self)


class Set(Plan):

    resource = Variable
    name = "set"

    def from_string(self, value):
        return value

    def to_lines(self, value):
        return [value]

    def execute(self, value):
        conf = self.runner.get_service(self.resource.config, "describe")
        if "." not in self.resource.name:
            raise errors.Error("You didn't specify a section")
        section, name = self.resource.name.rsplit(".", 1)
        c = conf.read()
        if not c.has_section(section):
            c.add_section(section)
        c.set(section, name, "\n".join(self.to_lines(value)))
        conf.write(c)


class Get(Plan):

    resource = Variable
    name = "get"

    def to_string(self, value):
        return str(value)

    def from_lines(self, value):
        assert len(value) == 1
        return value[0]

    def execute(self):
        conf = self.runner.get_service(self.resource.config, "describe")
        if "." not in self.resource.name:
            raise errors.Error("You didn't specify a section")
        section, name = self.resource.name.rsplit(".", 1)
        c = conf.read()

        try:
            return self.from_lines(c.get(section, name).splitlines()), True
        except (configparser.NoSectionError, configparser.NoOptionError):
            default = serializers.maybe(self.resource.default).render(
                self.runner,
                self.resource,
            )
            return default, False


class Refresh(Plan):

    resource = Variable
    name = "refresh"

    def execute(self):
        setter = self.runner.get_service(self.resource, "set")
        setter.execute(self.resource.default)


class VariableAsString(serializers.Serializer):

    def __init__(self, resource):
        self.resource = resource

    def render(self, runner, object):
        return runner.get_service(self.resource, "get").execute()[0]

    def dependencies(self, object):
        return frozenset((self.resource, ))