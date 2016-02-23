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
import subprocess
import sys

from docutils.core import publish_string
from docutils.writers import manpage

from botocore.docs.bcdoc.restdoc import ReSTDocument

from touchdown.core import errors, goals, map
from touchdown.core.workspace import Touchdownfile
from touchdown.core.selectors import Selector
from touchdown.frontends import ConsoleFrontend


USAGE = "%(prog)s [<selector> ...] <command> [parameters]"


class Action(object):

    def __init__(self, workspace, selectors, console, goal):
        self.workspace = workspace
        self.selectors = selectors
        self.goal = goal
        self.console = console
        self.parser = argparse.ArgumentParser(
            usage=USAGE,
            add_help=False,
        )
        self.parser.add_argument("--debug", default=False, action="store_true")
        self.parser.add_argument("--serial", default=False, action="store_true")
        self.parser.add_argument("--unattended", default=False, action="store_true")
        goal.setup_argparse(self.parser)

    def print_help(self):
        print("HELP")

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

    def __call__(self, *args):
        if len(args) == 1 and args[0] == "help":
            return self.print_help()
        args = self.parser.parse_args(args)
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


class SelectorOrAction(object):

    def __init__(self, workspace, selectors):
        self.workspace = workspace
        self.selectors = selectors
        self.parser = argparse.ArgumentParser(
            usage=USAGE,
            add_help=False,
        )
        self.parser.add_argument('selector', action='store')

    def print_help(self):
        doc = ReSTDocument()
        doc.style.h1("Touchdown")

        doc.style.start_p()
        doc.write("The current expression is: {!r}".format(" ".join(self.selectors)))
        doc.style.end_p()

        matches = Selector(self.workspace).find(self.selectors)
        if not matches:
            doc.style.start_p()
            doc.write("This expression has *no* matches")
            return

        doc.style.h2("Available commands")
        doc.style.start_p()
        doc.write("The following subcommands are available for the resources selected:")
        doc.style.end_p()
        doc.style.start_ul()
        for name, goal in goals.registered():
            for match in matches:
                if not hasattr(match, "meta") or name not in match.meta.plans:
                    break
            else:
                doc.style.li(name)
        doc.style.end_ul()

        doc.style.h2("Expression matches")
        doc.style.start_p()
        doc.write("This expression matches the following resources:")
        doc.style.end_p()
        doc.style.start_ul()
        for m in matches:
            doc.style.li(":".join((m.resource_name, getattr(m, "name", ""))))
        doc.style.end_ul()

        doc.style.h2("Outgoing references")
        doc.style.start_p()
        doc.write("This resource is dependended on by:")
        doc.style.end_p()
        depends = set()
        for node in matches:
            for dep in Selector(self.workspace).backward.map.get(node, set()):
                depends.add(":".join((dep.resource_name, getattr(dep, "name", ""))))

        depends = list(depends)
        depends.sort()
        doc.style.start_ul()
        [doc.style.li(r) for r in depends]
        doc.style.end_ul()

        doc.style.h2("Incoming references")
        doc.style.start_p()
        doc.write("This resource depends on:")
        doc.style.end_p()
        depends_on = set()
        for node in matches:
            for dep in Selector(self.workspace).forward.map.get(node, set()):
                depends_on.add(":".join((dep.resource_name, getattr(dep, "name", ""))))
        depends_on = list(depends_on)
        depends_on.sort()
        doc.style.start_ul()
        [doc.style.li(r) for r in depends_on]
        doc.style.end_ul()

        man = publish_string(doc.getvalue(), writer=manpage.Writer())
        p = subprocess.Popen(["groff", "-man", "-T", "ascii"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate(man)

        p = subprocess.Popen(['less', '-R'], stdin=subprocess.PIPE)
        p.communicate(stdout)

    def get_goal(self, goal, parents):
        for node in parents:
            if not hasattr(node, "meta") or goal not in node.meta.plans:
                return
        return goals.get(goal)

    def __call__(self, *args):
        parents = Selector(self.workspace).find(self.selectors)
        if not parents:
            print("No resources match the selectors '{}'".format(" ".join(self.selectors)))
            return

        if len(args) == 0:
            return self.print_help()

        known, leftover = self.parser.parse_known_args(args)

        if known.selector == "help":
            return self.print_help()

        goal = self.get_goal(known.selector, parents)
        if goal:
            return Action(self.workspace, self.selectors, ConsoleFrontend(), goal)(*leftover)

        return SelectorOrAction(self.workspace, self.selectors + [known.selector])(*leftover)


def main(argv=None):
    workspace = Touchdownfile()
    workspace.load()

    argv = argv or sys.argv[1:]
    return SelectorOrAction(workspace, [])(*argv)


if __name__ == "__main__":
    main()
