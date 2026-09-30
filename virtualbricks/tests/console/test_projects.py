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

"""The commands of the projects, and the front end they open them with."""

import os

from virtualbricks.config.report import Report
from virtualbricks.console import projects as console_projects
from virtualbricks.tests import FakeTrash, use_workspace
from virtualbricks.tests.console import ConsoleTestCase


class FakeFrontend:
    def __init__(self):
        self.calls = []

    def open(self, name, factory):
        self.calls.append(("open", name))
        return Report()

    def new(self, name, factory):
        self.calls.append(("new", name))

    def save(self, factory):
        self.calls.append(("save",))


class ProjectsTestCase(ConsoleTestCase):

    def setUp(self):
        super().setUp()
        self.workspace = use_workspace(self, os.path.abspath(self.mktemp()))
        os.makedirs(self.workspace.path)
        self.workspace.create("lab", "# The lab\n\nTwo routers")
        self.workspace.open("lab", self.factory)


class TestTheWorkspace(ProjectsTestCase):

    def test_list_and_show(self):
        self.workspace.create("other")
        self.assertEqual(
            self.run_line("project list"), ["* lab    The lab", "  other"]
        )
        self.factory.new_brick("switch", "sw1")
        self.assertEqual(
            self.run_line("project show"),
            [
                "lab",
                os.path.join(self.workspace.path, "lab"),
                "1 bricks, 0 events, 0 images",
            ],
        )

    def test_open_new_and_save(self):
        self.workspace.create("other")
        self.factory.new_brick("switch", "sw1")
        self.assertEqual(self.run_line("project open other"), [])
        self.assertEqual(self.workspace.current.name, "other")
        self.assertEqual(list(self.factory.bricks), [])
        self.assertEqual(self.run_line("project new third"), [])
        self.assertEqual(self.workspace.current.name, "third")
        self.factory.new_brick("switch", "sw9")
        self.assertEqual(self.run_line("project save"), [])
        self.assertEqual(self.workspace.summary("third").bricks, {"switch": 1})
        # lab kept its switch when other opened
        self.assertEqual(self.workspace.summary("lab").bricks, {"switch": 1})

    def test_what_is_wrong(self):
        self.assertEqual(
            self.fails("project open nope"), "No project named nope"
        )
        self.assertEqual(
            self.fails("project new lab"),
            "lab: A project with this name already exists",
        )
        brick = self.factory.new_brick("switch", "sw1")
        brick.proc = object()
        self.assertEqual(
            self.fails("project new other"), "sw1 is running: stop it first"
        )
        other = self.factory.new_brick("switch", "sw2")
        other.proc = object()
        self.assertEqual(
            self.fails("project open lab"),
            "sw1 and sw2 are running: stop them first",
        )

    def test_rename_and_duplicate(self):
        self.assertEqual(self.run_line("project duplicate lab lab2"), [])
        self.assertEqual(self.run_line("project rename lab2 lab3"), [])
        self.assertEqual(self.workspace.names(), ["lab", "lab3"])
        self.assertEqual(
            self.fails("project rename lab3 lab"),
            "lab: A project with this name already exists",
        )

    def test_delete(self):
        self.workspace.create("old")
        self.assertEqual(
            self.fails("project delete old"),
            "There is no trash here: --force deletes old for good",
        )
        self.assertEqual(
            self.fails("project delete lab --force"),
            "lab is open: open another first",
        )
        self.assertEqual(self.run_line("project delete old --force"), [])
        self.assertEqual(self.workspace.names(), ["lab"])
        self.workspace.create("older")
        trash = FakeTrash()
        self.workspace.trasher = trash
        self.assertEqual(
            self.run_line("project delete older"), ["older is in the trash"]
        )
        self.assertEqual(
            trash.trashed, [os.path.join(self.workspace.path, "older")]
        )


class TestTheFrontend(ProjectsTestCase):

    def test_through_the_frontend(self):
        # the windows open and save projects their own way
        frontend = FakeFrontend()
        self.patch(console_projects, "frontend", frontend)
        self.workspace.create("other")
        self.run_line("project open other")
        self.run_line("project new third")
        self.run_line("project save")
        self.assertEqual(
            frontend.calls, [("open", "other"), ("new", "third"), ("save",)]
        )

    def test_use_frontend(self):
        self.patch(console_projects, "frontend", console_projects.frontend)
        frontend = FakeFrontend()
        console_projects.use_frontend(frontend)
        self.assertIs(console_projects.frontend, frontend)
