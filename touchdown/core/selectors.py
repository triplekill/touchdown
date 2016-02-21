# Copyright 2016 Isotoma Limited
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

from touchdown.core.dependencies import DependencyMap


class Start(object):

    resource_name = "all-resources"
    dot_ignore = True

    def __init__(self, tips):
        self.dependencies = set(tips)


class Selector(object):

    def __init__(self, workspace):
        self.workspace = workspace
        self.dependencies = DependencyMap(workspace)

    def is_node(self, node, expression):
        """ Returns True if a given node matches a selection expression """
        if ":" in expression:
            resource_class, resource_name = expression.split(":", 1)
        else:
            resource_class, resource_name = '', expression

        if resource_class and resource_class != node.resource_name:
            return False

        if resource_name and resource_name != getattr(node, "name", None):
            return False
        return True

    def find_all_tips(self):
        """ Yield all nodes that have no dependencies """
        for node, dependencies in self.dependencies.items():
            if len(dependencies) > 0:
                continue
            yield node

    def find_matching(self, node, selector):
        """ Starting from node, traverse the graph looking for matches of selector """
        queue = [node]
        visited = set()

        while queue:
            node = queue.pop(0)
            for dep in node.dependencies:
                if dep not in visited and dep not in queue:
                    queue.append(dep)
            if self.is_node(node, selector):
                yield node
            visited.add(node)

    def find(self, selectors):
        queue = set((Start(self.find_all_tips()), ))
        found = set()
        for selector in selectors:
            while queue:
                node = queue.pop()
                found.update(self.find_matching(node, selector))
            queue = found
            found = set()

        matches = list(queue)
        matches.sort(key=lambda r: ":".join((r.resource_name, getattr(r, "name", ""))))
        return matches
