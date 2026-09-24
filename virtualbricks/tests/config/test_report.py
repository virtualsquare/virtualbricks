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

from twisted.trial import unittest

from virtualbricks.config import ERROR, INFO, WARNING, Message, Report
from virtualbricks.tests import FakeLogger


class TestMessage(unittest.TestCase):

    def test_str_with_where(self):
        message = Message(WARNING, "is odd", "bricks.sw1")
        self.assertEqual(str(message), "bricks.sw1: is odd")

    def test_str_without_where(self):
        self.assertEqual(str(Message(INFO, "done")), "done")


class TestReport(unittest.TestCase):

    def setUp(self):
        self.report = Report()

    def test_empty(self):
        self.assertEqual(len(self.report), 0)
        self.assertEqual(list(self.report), [])
        self.assertFalse(self.report.has_errors)

    def test_levels(self):
        self.report.info("a")
        self.report.warning("b", "x")
        self.report.warning("c")
        self.report.error("d", "y")
        self.assertEqual(
            [m.level for m in self.report], [INFO, WARNING, WARNING, ERROR]
        )
        self.assertEqual(self.report.warnings, 2)
        self.assertEqual(self.report.errors, 1)
        self.assertEqual(self.report.count(INFO), 1)
        self.assertTrue(self.report.has_errors)
        self.assertEqual(self.report.messages[1], Message(WARNING, "b", "x"))

    def test_extend(self):
        other = Report()
        other.error("bad")
        self.report.info("fine")
        self.report.extend(other)
        self.assertEqual([m.text for m in self.report], ["fine", "bad"])

    def test_log(self):
        self.report.info("a", "one")
        self.report.warning("b")
        self.report.error("c", "three")
        logger = FakeLogger()
        self.report.log(logger)
        self.assertEqual(logger.levels(), ["info", "warn", "error"])
        self.assertEqual(logger.formatted(), ["one: a", "b", "three: c"])
