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

import os

from virtualbricks import switches, errors, settings
from virtualbricks.tests import unittest, stubs

settings.load()


class TestSwitch(unittest.TestCase):

    def test_socks(self):
        factory = stubs.FactoryStub()
        sw = switches.Switch(factory, "test_switch")
        self.assertEqual(len(sw.socks), 1)
        self.assertIn(sw.socks[0], factory.socks)

    def test_base(self):
        sw = switches.Switch(stubs.FactoryStub(), "test_switch")
        self.assertEqual(len(sw.socks), 1)
        self.assertEqual(sw.socks[0].path, sw.path())
        self.assertIs(sw.proc, None)

    def test_live_management_callbacks(self):
        sw = switches.Switch(stubs.FactoryStub(), "test_switch")
        output = []
        sw.send = output.append
        sw.set({"numports": 33})
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0], "port/setnumports 33\n")
        sw.config["numports"] = 33
        self.assertEqual(len(output), 1)

    def test_args(self):
        sw1 = switches.Switch(stubs.FactoryStub(), "test_switch")
        self.assertEqual(sw1.args(),
            [
                "/usr/bin/vde_switch",
                "-n", "32",
                "-s", os.path.join(settings.VIRTUALBRICKS_HOME, "test_switch.ctl"),
                "-M", os.path.join(settings.VIRTUALBRICKS_HOME, "test_switch.mgmt")
            ]
        )


class TestSwitchWrapper(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.sw = switches.SwitchWrapper(self.factory, "test_switch")

    def test_socks(self):
        self.assertEqual(len(self.sw.socks), 1)
        self.assertIn(self.sw.socks[0], self.factory.socks)

    def test_poweron(self):
        """
        SwitchWrapper uses a custom poweron method, assure that it respect the
        interface.
        """
        self.sw.proc = object()
        result = []
        self.sw.poweron().addCallbacks(result.append)
        self.assertEqual(result, [self.sw])
        self.sw.proc = None
        sockfile = self.mktemp()
        open(sockfile, "w").close()
        self.sw.config["path"] = sockfile
        self.sw.poweron().addCallback(result.append)
        self.assertEqual(result, [self.sw] * 2)
        self.sw.proc = None
        self.sw.config["path"] = ""
        deferred = self.sw.poweron()
        self.assertFailure(deferred, errors.BadConfigError)

    def test_poweroff(self):
        self.sw.proc = object()
        result = []
        self.sw.poweroff().addCallback(result.append)
        self.assertIs(self.sw.proc, None)
        self.assertEqual(result, [(self.sw, None)])
