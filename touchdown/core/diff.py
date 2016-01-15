# Copyright 2014 Isotoma Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, softwserializersdistributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


class ValueDiff(object):

    def __init__(self, remote_value, local_value):
        self.remote_value = remote_value
        self.local_value = local_value

    def matches(self):
        return self.remote_value == self.local_value

    def lines(self):
        return ["{0.remote_value!r} => {0.local_value!r}".format(self)]

    def __str__(self):
        return '\n'.join(self.lines())


class AttributeDiff(object):

    def __init__(self):
        self.diffs = []

    def add(self, field, diff):
        if not diff.matches():
            self.diffs.append((field, diff))

    def matches(self):
        return len(self) == 0

    def lines(self):
        for field, diff in self.diffs:
            yield "{}: ".format(field)
            for line in diff.lines():
                yield "    {}".format(line)

    def __len__(self):
        return len(self.diffs)

    def __str__(self):
        return '\n'.join(self.lines())
