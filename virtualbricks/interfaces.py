# -*- test-case-name: virtualbricks.tests.test_factory -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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
import logging

from zope.interface import interface, declarations, Interface, Attribute
from zope.interface.adapter import AdapterRegistry


log = logging.getLogger()


# from twisted.python.components import registerAdapter
globalRegistry = AdapterRegistry()
ALLOW_DUPLICATES = True


def registerAdapter(adapterFactory, origInterface, *interfaceClasses):
    """Register an adapter class.

    An adapter class is expected to implement the given interface, by
    adapting instances implementing 'origInterface'. An adapter class's
    __init__ method should accept one parameter, an instance implementing
    'origInterface'.
    """
    self = globalRegistry
    assert interfaceClasses, "You need to pass an Interface"
    global ALLOW_DUPLICATES

    # deal with class->interface adapters:
    if not isinstance(origInterface, interface.InterfaceClass):
        origInterface = declarations.implementedBy(origInterface)

    for interfaceClass in interfaceClasses:
        factory = self.registered([origInterface], interfaceClass)
        if factory is not None and not ALLOW_DUPLICATES:
            raise ValueError("an adapter (%s) was already registered." % (factory, ))
    for interfaceClass in interfaceClasses:
        self.register([origInterface], interfaceClass, '', adapterFactory)


def _addHook(registry):
    """
    Add an adapter hook which will attempt to look up adapters in the given
    registry.

    @type registry: L{zope.interface.adapter.AdapterRegistry}

    @return: The hook which was added, for later use with L{_removeHook}.
    """
    lookup = registry.lookup1
    def _hook(iface, ob):
        factory = lookup(declarations.providedBy(ob), iface)
        if factory is None:
            return None
        else:
            return factory(ob)
    interface.adapter_hooks.append(_hook)
    return _hook


_addHook(globalRegistry)


class InterfaceLogger:

    def __init__(self, original, interface):
        self.original = original
        self.interface = interface

    def __getattr__(self, name):
        if name not in self.interface:
            log.warning("Requested a non-interface (%s) method: %s\n%s",
                        self.interface.__name__, name,
                        "\n".join("%s:%d %s" % (fn, l, fun) for
                                  fn, l, fun, t in
                                  reversed(traceback.extract_stack())))
        try:
            return getattr(self.original, name)
        except AttributeError:
            raise AttributeError(name)


class IMenu(Interface):

    def popup(button, time):
        """Pop up a menu for a specific brick."""


class IJobMenu(IMenu):
    pass


class IConfigController(Interface):

    def get_view(gui):
        """Return the configuration panel for the given brick or event."""

    def configure_brick(gui):
        """Configure the brick as setted in the panel."""


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
    homehost = Attribute("")
    cfg = Attribute("")
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
