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

"""The help buttons: their window, and the text of their topic."""

from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui import help


class TestHelp(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.help = help.Help()
        self.button = Gtk.Button(label="?")
        self.addCleanup(self.button.destroy)

    def text(self, window):
        buffer = window.textbuffer
        return buffer.get_text(
            buffer.get_start_iter(), buffer.get_end_iter(), False
        )

    def test_a_topic(self):
        self.assertTrue(self.help.on_help_button_clicked(self.button, "delay"))
        window = self.help.window
        self.addCleanup(lambda: window.window.destroy())
        self.assertEqual(self.text(window), self.help.get_help("delay"))
        self.assertTrue(self.text(window))

    def test_one_window(self):
        self.help.on_help_button_clicked(self.button, "delay")
        window = self.help.window
        self.addCleanup(lambda: window.window.destroy())
        self.help.on_help_button_clicked(self.button, "loss")
        self.assertIs(self.help.window, window)
        self.assertEqual(self.text(window), self.help.get_help("loss"))

    def test_closed(self):
        self.help.on_help_button_clicked(self.button, "delay")
        first = self.help.window
        first.window.destroy()
        self.assertIsNone(self.help.window)
        # a new one, the next time
        self.help.on_help_button_clicked(self.button, "delay")
        self.addCleanup(lambda: self.help.window.window.destroy())
        self.assertIsNot(self.help.window, first)

    def test_no_such_topic(self):
        self.assertRaises(help.NoHelpFoundError, self.help.get_help, "nothing")

    def test_the_buttons_of_the_channel_emulator(self):
        # each topic has its file
        from virtualbricks.gui.mainwindow.bricks.config.netemuconfig import (
            NetemuConfigController,
        )

        for button in NetemuConfigController.help_buttons:
            topic = button.removesuffix("_help_button")
            self.assertTrue(self.help.get_help(topic), topic)
