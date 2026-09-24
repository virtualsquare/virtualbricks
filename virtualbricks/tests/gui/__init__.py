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

"""Helpers for the tests of the windows; they build no window on screen."""

import os

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks import project, tools
from virtualbricks.tests import (
    FakeLogger,
    isolate,
    make_factory,
    reset_settings,
)

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    has_display = Gtk.init_check()[0]
except (ImportError, ValueError):  # pragma: no cover
    has_display = False


class FakeGui:
    """The main window, as the dialogs see it."""

    def __init__(self, factory):
        self.brickfactory = factory
        self.systray = []

    def start_systray(self):
        self.systray.append("start")

    def stop_systray(self):
        self.systray.append("stop")


class GuiTestCase(unittest.TestCase):
    """A window test with its own settings, factory and workspace."""

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.ksm = []

        def set_ksm(enable):
            self.ksm.append(enable)
            return defer.succeed(enable)

        self.patch(tools, "set_ksm", set_ksm)
        self.factory = make_factory(self)
        self.manager = project.ProjectManager(
            os.path.join(self.root, "workspace")
        )
        self.patch(project, "manager", self.manager)
        self.patch(project, "logger", FakeLogger())

    def folder(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path, exist_ok=True)
        return path

    def image(self, name):
        path = os.path.join(self.root, name + ".qcow2")
        with open(path, "w"):
            pass
        return self.factory.new_disk_image(name, path)
