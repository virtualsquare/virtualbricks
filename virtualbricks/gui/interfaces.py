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

from zope.interface import Interface

from virtualbricks.interfaces import registerAdapter


__all__ = ["IMenu", "IJobMenu", "IConfigController", "registerAdapter"]


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

    def __call__(self):
        """Return YES, NO or MAYBE if the prerequisite is satisfied."""


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
