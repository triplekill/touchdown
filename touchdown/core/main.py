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

from __future__ import print_function

import argparse
import inspect
import logging
import sys

from touchdown.core import errors, goals, map
from touchdown.core.workspace import Touchdownfile
from touchdown.core.selectors import Selector
from touchdown.frontends import ConsoleFrontend


class SubCommand(object):

    def __init__(self, goal, workspace, console):
        self.goal = goal
        self.workspace = workspace
        self.console = console

    def get_args_and_kwargs(self, callable, namespace):
        argspec = inspect.getargspec(callable)
        args = []
        for arg in argspec.args[1:]:
            args.append(getattr(namespace, arg))
        kwargs = {}
        for k, v in namespace._get_kwargs():
            if k not in argspec.args and argspec.keywords:
                kwargs[k] = v
        return args, kwargs

    def __call__(self, args):
        try:
            g = self.goal(
                self.workspace,
                self.console,
                map.ParallelMap if not args.serial else map.SerialMap
            )
            self.console.start(self, g)
            args, kwargs = self.get_args_and_kwargs(g.execute, args)
            return g.execute(*args, **kwargs)
        except errors.Error as e:
            self.console.echo(str(e))
            sys.exit(1)
        finally:
            self.console.finish()


def configure_parser(parser, workspace, console):
    parser.add_argument("--debug", default=False, action="store_true")
    parser.add_argument("--serial", default=False, action="store_true")
    parser.add_argument("--unattended", default=False, action="store_true")

    sub = parser.add_subparsers()
    for name, goal in goals.registered():
        p = sub.add_parser(name, help=getattr(goal, "__doc__", ""))
        goal.setup_argparse(p)
        p.set_defaults(func=SubCommand(
            goal,
            workspace,
            console,
        ))


class SelectorAction(argparse.Action):

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        kwargs['nargs'] = '*'
        super(SelectorAction, self).__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        root = Selector(parser.workspace).find(values)
        if not root:
            raise ValueError("No resources match the selectors {}".format(values))
        setattr(namespace, self.dest, root)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Manage your infrastructure")
    parser.workspace = Touchdownfile()
    parser.workspace.load()
    parser.add_argument('selectors', action=SelectorAction)
    console = ConsoleFrontend()
    configure_parser(parser, parser.workspace, console)
    args = parser.parse_args(argv or sys.argv[1:])

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")

    console.interactive = not args.unattended

    args.func(args)


if __name__ == "__main__":
    main()
