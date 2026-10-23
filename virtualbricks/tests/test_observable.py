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


"""The signals, and an observable muted."""

from twisted.trial import unittest

from virtualbricks.observable import Observable, Signal


class TestMuted(unittest.TestCase):

    def setUp(self):
        self.observable = Observable()
        self.changed = Signal(self.observable, "changed")
        self.heard = []
        self.changed.connect(self.heard.append)

    def test_heard(self):
        self.changed.notify("a")
        self.assertEqual(self.heard, ["a"])

    def test_muted(self):
        with self.observable.muted():
            self.changed.notify("a")
        self.changed.notify("b")
        self.assertEqual(self.heard, ["b"])

    def test_every_signal_of_the_observable(self):
        removed = Signal(self.observable, "removed")
        removed.connect(self.heard.append)
        with self.observable.muted():
            self.changed.notify("a")
            removed.notify("b")
        self.assertEqual(self.heard, [])

    def test_only_its_own_signals(self):
        other = Signal(Observable(), "changed")
        other.connect(self.heard.append)
        with self.observable.muted():
            other.notify("a")
        self.assertEqual(self.heard, ["a"])

    def test_nested(self):
        with self.observable.muted():
            with self.observable.muted():
                pass
            self.changed.notify("a")
        self.changed.notify("b")
        self.assertEqual(self.heard, ["b"])

    def test_an_error_leaves_it_heard(self):
        with self.assertRaises(ValueError):
            with self.observable.muted():
                raise ValueError("out of the block")
        self.changed.notify("a")
        self.assertEqual(self.heard, ["a"])
