# -*- test-case-name: virtualbricks.tests.gui.test_help -*-
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

import os
import errno

from gi.repository import Gtk
from zope.interface import implementer

from virtualbricks.gui import graphics, interfaces


class HelpError(Exception):
    pass


class NoHelpFoundError(HelpError):
    pass


class UnknonwHelpError(HelpError):
    pass


class HelpWindow:

    def __init__(self):
        self.window = window = Gtk.Window()
        window.set_resizable(True)
        window.set_size_request(350, 300)
        window.set_title("Virtualbricks - help")
        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.set_cursor_visible(False)
        textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textbuffer = textview.get_buffer()
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(textview)
        window.add(sw)
        window.show_all()

    def set_text(self, text):
        self.textbuffer.set_text(text)

    def present(self):
        self.window.present()


@implementer(interfaces.IHelp)
class Help:

    window_factory = HelpWindow
    window = None

    def get_help(self, argument):
        filename = graphics.get_data_filename(
            os.path.join("help", argument + ".txt")
        )
        if filename is None:
            # no such resource
            raise NoHelpFoundError(argument)
        try:
            with open(filename) as fp:
                return fp.read()
        except IOError as e:
            if e.errno == errno.ENOENT:
                raise NoHelpFoundError(argument)
            raise UnknonwHelpError(e)

    def destroy_window(self, window):
        self.window = None

    def show_help_window(self, text):
        window = self.window
        if not window:
            self.window = window = self.window_factory()
            window.window.connect("destroy", self.destroy_window)
        window.set_text(text)
        window.present()
        return window

    def on_help_button_clicked(self, button, topic):
        """Show the help on topic, the file help/<topic>.txt."""

        self.show_help_window(self.get_help(topic))
        return True
