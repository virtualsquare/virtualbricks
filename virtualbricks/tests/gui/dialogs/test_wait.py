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

"""The window that says what the main window waits for."""

from twisted.internet import defer, task
from twisted.trial import unittest

from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.dialogs.wait import PULSE, WaitWindow


class TestWaitWindow(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.parent = Gtk.Window()
        self.addCleanup(self.parent.destroy)
        self.clock = task.Clock()
        self.destroyed = []

    def wait_for(self, deferred):
        """The window, waiting for deferred, and what wait_for() returned."""

        wait = WaitWindow("Suspending vm…")
        wait.pulsing.clock = self.clock
        wait.window.connect("destroy", self.destroyed.append)
        self.addCleanup(wait.window.destroy)
        return wait, wait.wait_for(deferred, self.parent)

    def assertDone(self, wait):
        self.assertTrue(self.parent.get_sensitive())
        self.assertEqual(self.destroyed, [wait.window])
        self.assertFalse(wait.pulsing.running)
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_waiting(self):
        wait, waiting = self.wait_for(defer.Deferred())
        self.assertFalse(self.parent.get_sensitive())
        self.assertTrue(wait.window.get_visible())
        self.assertTrue(wait.window.get_modal())
        self.assertIs(wait.window.get_transient_for(), self.parent)
        self.assertEqual(wait.label.get_text(), "Suspending vm…")
        self.assertTrue(wait.pulsing.running)
        self.clock.advance(PULSE)
        self.assertTrue(wait.pulsing.running)
        self.assertEqual(self.destroyed, [])

    def test_done(self):
        deferred = defer.Deferred()
        wait, waiting = self.wait_for(deferred)
        self.clock.advance(PULSE)
        deferred.callback("suspended")
        self.assertEqual(self.successResultOf(waiting), "suspended")
        self.assertDone(wait)

    def test_failed(self):
        deferred = defer.Deferred()
        wait, waiting = self.wait_for(deferred)
        deferred.errback(RuntimeError("Cannot find suspend point."))
        self.failureResultOf(waiting, RuntimeError)
        self.assertDone(wait)

    def test_done_already(self):
        wait, waiting = self.wait_for(defer.succeed("suspended"))
        self.assertEqual(self.successResultOf(waiting), "suspended")
        self.assertDone(wait)
