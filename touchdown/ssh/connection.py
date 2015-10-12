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

import time

from touchdown.core import adapters, argument, errors, plan, serializers, workspace

try:
    from . import client
    from paramiko import ssh_exception
except ImportError:
    client = None

from touchdown.provisioner import Target


class Instance(adapters.Adapter):
    pass


class Connection(Target):

    resource_name = "ssh_connection"

    name = argument.String()
    username = argument.String(default="root", field="username")
    password = argument.String(field="password")
    private_key = argument.String(field="pkey", serializer=serializers.Identity())
    hostname = argument.String(field="hostname")
    instance = argument.Resource(Instance, field="hostname", serializer=serializers.Resource())
    port = argument.Integer(field="port", default=22)

    proxy = argument.Resource("touchdown.ssh.connection.Connection")

    root = argument.Resource(workspace.Workspace)

    def clean_private_key(self, private_key):
        if private_key and client:
            return client.private_key_from_string(private_key)
        raise errors.InvalidParameter("Invalid SSH private key")


class ConnectionPlan(plan.Plan):

    name = "describe"
    resource = Connection
    _client = None

    def get_client(self):
        if self._client:
            return self._client

        cli = client.Client(self)

        kwargs = serializers.Resource().render(self.runner, self.resource)

        if self.resource.proxy:
            self.echo("Setting up connection proxy via {}".format(self.resource.proxy))
            proxy = self.runner.get_plan(self.resource.proxy)
            transport = proxy.get_client().get_transport()
            self.echo("Setting up proxy channel to {}".format(kwargs['hostname']))
            for i in range(20):
                try:
                    kwargs['sock'] = transport.open_channel(
                        'direct-tcpip',
                        (kwargs['hostname'], kwargs['port']),
                        ('', 0)
                    )
                    break
                except ssh_exception.ChannelException:
                    time.sleep(i)
                    continue

            if 'sock' not in kwargs:
                raise errors.Error("Error setting up proxy channel to {} after 20 tries".format(kwargs['hostname']))

            self.echo("Proxy setup")

        if not self.resource.password and not self.resource.private_key:
            kwargs['look_for_keys'] = True
            kwargs['allow_agent'] = True

        args = ["hostname={}".format(kwargs['hostname']), "username={}".format(kwargs['username'])]
        if self.resource.port != 22:
            args.append("port={}".format(kwargs['port']))

        self.echo("Establishing ssh connection ({})".format(", ".join(args)))
        cli.connect(**kwargs)

        self.echo("Got connection")

        self._client = cli

        return cli

    def get_actions(self):
        if not client:
            raise errors.Error("Paramiko library is required to perform operations involving ssh")
        return []
