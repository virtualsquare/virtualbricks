# -*- test-case-name: virtualbricks.tests.bricks.test_eventaction -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""An action of an event: a console command or a shell command."""

from virtualbricks import console
from virtualbricks.config import Kind


class EventAction(Kind):
    """A console command ("vb") or a shell command ("shell")."""

    kinds = {"vb": console.VbShellCommand, "shell": console.ShellCommand}

    def check(self, value):
        if not isinstance(value, tuple(self.kinds.values())):
            raise ValueError(f"{value!r} is not an event action")

    def to_data(self, value):
        for kind, cls in self.kinds.items():
            if isinstance(value, cls):
                return {"kind": kind, "command": str(value)}

    def from_data(self, data, report, where):
        if not isinstance(data, dict):
            raise ValueError(f"{data!r} is not a table")
        kind = data.get("kind")
        command = data.get("command")
        if kind not in self.kinds:
            raise ValueError(f"{kind!r} is not vb or shell")
        if not isinstance(command, str):
            raise ValueError(f"{command!r} is not a command")
        for key in data.keys() - {"kind", "command"}:
            report.warning("unknown field, dropped", f"{where}.{key}")
        return self.kinds[kind](command)

    def format(self, value):
        return _describe_action(value)


def _describe_action(action):
    if isinstance(action, console.ShellCommand):
        return f'shell "{action}"'
    return f'vb "{action}"'
