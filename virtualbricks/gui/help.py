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

import os
import errno
import re

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from zope.interface import implementer

from virtualbricks.gui import graphics, interfaces


__metaclass__ = type


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

    def do_destroy(self, window):
        self.window = None

    def set_text(self, text):
        self.textbuffer.set_text(text)

    def on_destroy(self, callable, *args):
        self.window.connect("destroy", callable, *args)

    def present(self):
        self.window.present()


@implementer(interfaces.IHelp)
class Help:

    RE = re.compile("^(\w+)_help_button$")
    window_factory = HelpWindow
    window = None

    def get_help(self, argument):
        try:
            path = os.path.join("help", argument + ".txt")
            with open(graphics.get_data_filename(path)) as fp:
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
            window.on_destroy(self.destroy_window)
        window.set_text(text)
        window.present()
        return window

    def on_help_button_clicked(self, button):
        match = self.RE.match(Gtk.Buildable.get_name(button))
        if match:
            self.show_help_window(self.get_help(match.group(1)))
            return True
