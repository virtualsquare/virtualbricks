import os
import errno
import re

import gtk

from virtualbricks.gui import graphics


class HelpError(Exception):
    pass


class NoHelpFoundError(HelpError):
    pass


class UnknonwHelpError(HelpError):
    pass


class HelpWindow:

    def __init__(self):
        self.window = window = gtk.Window()
        window.set_resizable(True)
        window.set_size_request(350, 300)
        window.set_title("Virtualbricks - help")
        textview = gtk.TextView()
        textview.set_editable(False)
        textview.set_cursor_visible(False)
        textview.set_wrap_mode(gtk.WRAP_WORD)
        self.textbuffer = textview.get_buffer()
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
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


class Help:

    RE = re.compile("^(\w+)_help_button$")
    window_factory = HelpWindow
    window = None

    def get_help(self, argument):
        try:
            path = os.path.join("data", "help", argument + ".txt")
            with open(graphics.get_filename("virtualbricks.gui", path)) as fp:
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
        match = self.RE.match(gtk.Buildable.get_name(button))
        if match:
            self.show_help_window(self.get_help(match.group(1)))
            return True
