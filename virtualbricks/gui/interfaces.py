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

from zope.interface import Interface, Attribute

from virtualbricks.interfaces import registerAdapter


__all__ = ["registerAdapter", "IMenu", "IJobMenu", "IConfigController",
           "IState", "IControl", "IStateManager"]


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


class IPrerequisite(Interface):

    def __call__():
        """
        @return: YES, NO or MAYBE if the prerequisite is satisfied.
        @rtype: C{bool}
        """


class IState(Interface):
    """An object that check all prerequisites and manage the controls."""

    def add_prerequisite(prerequisite):
        """
        Add a prerequisite.

        @param prerequisite: A prerequisite.
        @type prerequisite: L{IPrerequisite}
        """

    def add_control(control):
        """
        Add a control.

        @param control: The control.
        @type contro: L{IControl}
        """


class IControl(Interface):
    """Control a widget."""

    def react(enable):
        """
        Adjust a widget based on the result of the prerequisites.

        @param enable: C{True} if the widget should be enabled or C{False}
            otherwise.
        @type enable: C{bool}
        """


class IStateManager(Interface):
    """A collection of states."""

    def add_state(state):
        """
        Add a state to the collection.

        @param state: the state to add.
        @type state: L{IState}
        """


class IHelp(Interface):

    def get_help(argument):
        """Return the help for the given argument or raise an exception."""

    def show_help_window(text):
        """Show the help window with the text specified."""

    def on_help_button_clicked(button):
        """
        Callback that can be used to open the help window and show the help
        based on the name of the button.
        """


class IBindingList(Interface):

    changed = Attribute("IEvent, emitted when an item is changed")
    added = Attribute("IEvent, emitted when an item is added")
    removed = Attribute("IEvent, emitted when an item is removed")
