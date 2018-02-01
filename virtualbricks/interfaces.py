# -*- test-case-name: virtualbricks.tests.test_factory -*-
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


import traceback

from zope.interface import Interface, Attribute
from twisted.python.components import registerAdapter

from virtualbricks import log


__all__ = ["registerAdapter", "InterfaceLogger", "IBrick", "IPlug", "IBuilder"]

logger = log.Logger()
non_interface = log.Event("Requested a non-interface ({interface}) method: "
                          "{method}\n{traceback}")


class InterfaceLogger:

    def __init__(self, original, interface):
        self.original = original
        self.interface = interface

    def __getattr__(self, name):
        if name not in self.interface:
            tb = lambda: "\n".join("{0}:{1} {2}".format(fn, l, fun) for
                                   fn, l, fun, t in
                                   reversed(traceback.extract_stack()))
            logger.warn(non_interface, interface=self.interface.__name__,
                        method=name, traceback=tb)
        try:
            return getattr(self.original, name)
        except AttributeError:
            raise AttributeError(name)


class IBrick(Interface):

    type = Attribute("The type name of the brick")
    name = Attribute("The name of the brick")
    proc = Attribute("""None or an object conform to \
                     C{twisted.internet.interfaces.IProcessTransport""")

    def get_type():
        """Return the type of brick."""

    def poweron():
        """Start the brick.

        Return a deferred that fires when the brick is started."""

    def poweroff():
        """Stop the brick.

        Return a deferred that fires when the brick is stopped."""

    def get_parameters():
        """Actually used only in the main tree to show the list of the
        parameters"""
        # XXX: remove this method

    def configure(attrlist):
        """Configure the brick"""

    def __eq__(other):
        """Compare two bricks"""
        # XXX: maybe should use is keyword?

    # to be controlled

    config_socks = Attribute("")
    socks = Attribute("")
    plugs = Attribute("")

    def connect(endpoint):
        pass

    def get_state():
        pass


class IPlug(Interface):

    def connected():
        """Check if the plug is properly connected and try to start the related
        bricks if it is not.

        Return a deferred that fires when the related are started."""


class IBuilder(Interface):

    def load_from(factory, item):
        """Return a new brick or link from the given item."""


class IProcess(Interface):
    """A class representing a process."""

    pid = Attribute("The exit value of the process. C{None} if process is not "
                    "termiated, C{int} otherwise.")

    def signal_process(signo):
        """
        Send a signal to the given process.

        @param signo: the signal to send to the process.
        @type signo: C{int} or one of "TERM", "KILL" or "INT"
        """

    def write(data):
        """Send data to the stdin of the process.

        @type data: C{str}
        """
