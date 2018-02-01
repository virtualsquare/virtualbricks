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

import StringIO
import textwrap

from zope.interface import implementer
from twisted.python import components
from twisted.internet import interfaces

from virtualbricks import console
from virtualbricks.tests import unittest, stubs


@implementer(interfaces.ITransport)
class FileTransportAdapter:

    def __init__(self, original):
        self.original = original

    def write(self, data):
        self.original.write(data)

    def writeSequence(self, sequence):
        self.original.write("".join(sequence))

    loseConnection = getPeer = getHost = lambda s: None

components.registerAdapter(FileTransportAdapter, StringIO.StringIO,
                           interfaces.ITransport)


class TestProtocol(unittest.TestCase):

    def setUp(self):
        self.factory = stubs.FactoryStub()
        self.stdout = StringIO.StringIO()

    def parse(self, cmd):
        console.parse(self.factory, cmd, self.stdout)

    def discard_output(self):
        self.stdout.seek(0)
        self.stdout.truncate()

    def get_value(self):
        ret = self.stdout.getvalue()
        self.discard_output()
        return ret[len(console.VBProtocol.intro) +
                   len(console.VBProtocol.prompt) + 1:
                   -len(console.VBProtocol.prompt)]

    def test_new_brick(self):
        self.parse("new stub test")
        self.discard_output()
        self.assertEquals(len(self.factory.bricks), 1)
        self.assertEquals(self.factory.bricks[0].name, "test")
        self.assertEquals(self.factory.bricks[0].get_type(), "Stub")
        self.parse("new stub t+")
        self.assertEqual(self.get_value(),
                         "Name must contains only letters, "
                         "numbers, underscores, hyphens and points, t+\n")
        cmd = "new stub"
        self.parse(cmd)
        self.assertEqual(self.get_value(), "invalid number of arguments\n")
        cmd = "new"
        self.parse(cmd)
        self.assertEqual(self.get_value(), "invalid number of arguments\n")
        self.flushLoggedErrors(TypeError)

    def test_new_event(self):
        self.parse("new event test_event")
        self.assertEquals(len(self.factory.events), 1)
        self.assertEquals(self.factory.events[0].name, "test_event")
        self.assertEquals(self.factory.events[0].get_type(), "Event")

    def test_quit_command(self):
        result = []
        self.factory.quit = lambda: result.append(True)
        self.parse("quit")
        self.assertEqual(result, [True])

    def test_help_command(self):
        self.discard_output()
        self.parse("help")
        self.assertEqual(self.get_value(),
                         textwrap.dedent(console.VBProtocol.__doc__) + "\n")
