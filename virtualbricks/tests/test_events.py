# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

from twisted.trial import unittest
from twisted.internet import defer

from virtualbricks import events, errors
from virtualbricks.tests import stubs, Skip


if False:  # pyflakes
    _ = str


class TestEvents(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.event = events.Event(self.factory, "test_event")

    def test_base(self):
        self.assertFalse(self.event.configured())
        self.assertEqual(self.event.get_state(), _("unconfigured"))
        self.event.config["actions"] = "add boo"
        self.event.config["delay"] = 1
        self.assertEqual(self.event.get_state(), _("off"))
        self.event.scheduled = True
        self.assertEqual(self.event.get_state(), _("running"))

    def test_change_state(self):
        self.assertRaises(errors.BadConfigError, self.event.toggle)
        self.event.config["actions"].append("")
        self.event.config["delay"] = 1024
        self.event.toggle()
        self.assertIsNot(self.event.scheduled, None)
        self.event.toggle()
        self.assertIs(self.event.scheduled, None)

    def test_get_parameters(self):
        self.event.config["actions"].append("do cucu")
        self.event.config["delay"] = 1024
        self.assertEqual(self.event.get_parameters(),
            'Delay: 1024; Actions: "do cucu"')
        self.event.config["actions"].append("undo cucu")
        self.assertEqual(self.event.get_parameters(),
            'Delay: 1024; Actions: "do cucu", "undo cucu"')

    @Skip("Use clock facilities")
    def test_poweron(self):
        self.assertRaises(errors.BadConfigError, self.event.poweron)
        self.event.config["actions"].append("")
        self.event.config["delay"] = 0.00001
        return self.event.poweron()

    def test_poweron2(self):
        self.event.config["actions"].append("")
        self.event.config["delay"] = 100
        self.event.poweron()
        s = self.event.scheduled
        self.event.poweron()
        self.assertIs(self.event.scheduled, s)
        self.event.poweroff()
