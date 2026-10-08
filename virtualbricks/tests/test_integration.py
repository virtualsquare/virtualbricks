# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

"""
The sample project, started with the programs installed here.

Each brick whose programs are installed must start and still be running;
the others must fail to start, saying what isn't installed. The tap and the
capture need root, and are left out without it. Skipped without QEMU,
qemu-img and vde_switch.
"""

import os
import shutil
import tempfile

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks.brickfactory import BrickFactory
from virtualbricks.tests import isolate, reset_settings, use_workspace
from virtualbricks.tests import sample

REQUIRED = ("qemu-system-x86_64", "qemu-img", "vde_switch")
MISSING = [name for name in REQUIRED if shutil.which(name) is None]


class TestSample(unittest.TestCase):

    if MISSING:
        skip = f"not installed: {', '.join(MISSING)}"
    timeout = 60

    def setUp(self):
        isolate(self)
        # the sockets need a folder with a short path
        run = tempfile.mkdtemp(prefix="vb-")
        self.addCleanup(shutil.rmtree, run, ignore_errors=True)
        os.environ["XDG_RUNTIME_DIR"] = run
        # no sound device is needed
        reset_settings(self, audio_driver="none")
        path = os.path.abspath(self.mktemp())
        os.makedirs(path)
        self.projects = use_workspace(self, path)
        self.factory = BrickFactory(defer.Deferred())

    def open_sample(self):
        """Make the sample, save it, and open it again from its file."""

        self.projects.create("sample")
        self.projects.open("sample", self.factory)
        sample.build(self.factory, self.projects.current.path)
        self.projects.save(self.factory)
        self.projects.close(self.factory)
        report = self.projects.open("sample", self.factory)
        self.assertEqual([str(message) for message in report], [])

    @defer.inlineCallbacks
    def test_start(self):
        self.open_sample()
        report = yield sample.run(self.factory)
        names = set(sample.PROGRAMS)
        if not sample.is_root():
            names -= set(sample.PRIVILEGED)
        self.assertEqual(set(report["bricks"]), names)
        for name, entry in report["bricks"].items():
            if sample.installed(name):
                self.assertEqual(entry["error"], "", entry)
                self.assertTrue(entry["running"], entry)
            else:
                self.assertFalse(entry["started"], entry)
                self.assertIn("isn't installed", entry["error"])
        # the event of sw1's start
        self.assertEqual(report["sw2_ports"], 8)
        self.assertEqual(
            sample.private_disks(), ["vm1_hda.cow", "vm1_hdb.cow"]
        )
        self.assertEqual(
            [brick.name for brick in self.factory.bricks if brick.proc], []
        )
