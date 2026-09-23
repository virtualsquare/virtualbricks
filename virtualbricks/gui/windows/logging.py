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

"""
Window with the messages of Virtualbricks.
"""

import os
import tempfile
import textwrap

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from twisted.internet import utils

from virtualbricks import __version__, log
from virtualbricks.gui.windows.base import _, _Window


logger = log.Logger()

bug_send = log.Event("Sending report bug")
bug_sent = log.Event("Report bug sent succefully")
bug_error = log.Event("{err}\nstderr:\n{stderr}")
bug_report_fail = log.Event("Report bug failed with code "
                            "{code}\nstderr:\n{stderr}")
bug_err_unknown = log.Event("Error on bug reporting")

BUG_REPORT_ERRORS = {
    1: "Error in command line syntax.",
    2: "One of the files passed on the command line did not exist.",
    3: "A required tool could not be found.",
    4: "The action failed.",
    5: "No permission to read one of the files passed on the command line."
}


class LoggingWindow(_Window):
    """
    The messages of Virtualbricks, with the buttons to save them, to clear them
    and to report a bug.
    """

    scroll_tolerance = 50

    def __init__(self, textbuffer):
        """
        :type textbuffer: Gtk.TextBuffer
        """

        self._textbuffer = textbuffer
        self._scroll_to_bottom = True
        self.build_ui()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``logging.ui``."""

        # window (Gtk.Window)
        self.window = Gtk.Window(
            width_request=700,
            height_request=450,
            can_focus=False,
            title=_("Virtualbricks logging"),
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            destroy_with_parent=True,
        )
        # TODO: empty Glade placeholder, nothing to create.
        box1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5,
        )
        scrolled_window1 = Gtk.ScrolledWindow(visible=True, can_focus=True)
        messages_text = Gtk.TextView(
            visible=True,
            can_focus=True,
            editable=False,
            wrap_mode=Gtk.WrapMode.WORD,
            left_margin=5,
            right_margin=5,
            cursor_visible=False,
        )
        scrolled_window1.add(messages_text)
        box1.pack_start(scrolled_window1, True, True, 0)
        button_box1 = Gtk.ButtonBox(
            visible=True,
            can_focus=False,
            spacing=5,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        report_bug_button = Gtk.LinkButton(
            label=_("report bug"),
            visible=True,
            can_focus=True,
            receives_default=True,
            has_tooltip=True,
            relief=Gtk.ReliefStyle.NONE,
        )
        button_box1.pack_start(report_bug_button, False, False, 0)
        button_box1.set_child_secondary(report_bug_button, True)
        save_button = Gtk.Button(
            label="gtk-save",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        button_box1.pack_start(save_button, False, False, 0)
        clear_button = Gtk.Button(
            label="gtk-clear",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        button_box1.pack_start(clear_button, False, False, 0)
        close_button = Gtk.Button(
            label="gtk-close",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        button_box1.pack_start(close_button, False, False, 0)
        box1.pack_start(button_box1, False, True, 0)
        self.window.add(box1)

        # Signals
        self.window.connect("destroy", self.on_window_destroy)
        scrolled_window1.connect(
            "scroll-event",
            self.on_scrolledwindow_scroll_event,
        )
        report_bug_button.connect(
            "activate-link",
            self.on_report_bug_button_activate_link,
        )
        save_button.connect("clicked", self.on_save_button_clicked)
        clear_button.connect("clicked", self.on_clear_button_clicked)
        close_button.connect("clicked", self.on_close_button_clicked)

        messages_text.set_buffer(self._textbuffer)
        self._on_textbuffer_changed_handler = self._textbuffer.connect(
            "changed",
            self.on_textbuffer_changed,
            messages_text,
        )
        self.scroll_to_end(messages_text, self._textbuffer)

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    def scroll_to_end(self, textview, textbuffer):
        """
        Scroll the view to the bottom.

        :type textview: Gtk.TextView
        :type textbuffer: Gtk.TextBuffer
        """

        textview.scroll_to_mark(
            mark=textbuffer.get_mark('end'),
            within_margin=0.0,
            use_align=True,
            xalign=0,  # left
            yalign=1  # bottom
        )

    def on_scrolledwindow_scroll_event(self, window, event):
        """
        Check if the window should automatically scroll to the bottom when new
        messages arrives.

        :type window: Gtk.ScrolledWindow
        :type event: Gdk.EventScroll
        :rtype: bool
        """

        adjustment = window.get_vadjustment()
        self._scroll_to_bottom = (
            adjustment.get_value()  # current offset from top
            >=
            adjustment.get_upper() -  # The maximum value for the adjustment
            adjustment.get_page_size() -  # The visible size
            self.scroll_tolerance
        )
        return False

    def on_textbuffer_changed(self, textbuffer, textview):
        """
        Scroll the view to the bottom, following the messages as the arrive,
        but only if the user did not scroll up.

        :type textbuffer: Gtk.TextBuffer
        :type textview: Gtk.TextView
        """

        if self._scroll_to_bottom:
            self.scroll_to_end(textview, textbuffer)
        return True

    def on_window_destroy(self, window):
        """
        Remove the handled we connected when the logging window opened.

        :type adjustment: Gtk.Window
        """

        self._textbuffer.disconnect(self._on_textbuffer_changed_handler)
        return True

    def on_close_button_clicked(self, button):
        """
        Close the window.

        :type adjustment: Gtk.Button
        """

        self.window.destroy()
        return True

    def on_clear_button_clicked(self, button):
        """
        Clean the logging window.

        :type adjustment: Gtk.Button
        """

        self._textbuffer.set_text('')
        return True

    def on_save_button_clicked(self, button):
        """
        Save the message to a file.

        :type adjustment: Gtk.Button
        """

        chooser = Gtk.FileChooserDialog(
            title=_('Save as...'),
            parent=self.window,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(
                'gtk-cancel', Gtk.ResponseType.CANCEL,
                'gtk-save', Gtk.ResponseType.OK
            )
        )
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect('response', self.on_saveDialog_response)
        chooser.show()
        return True

    def on_saveDialog_response(self, dialog, response_id):
        try:
            if response_id == Gtk.ResponseType.OK:
                text = self._textbuffer.get_property('text')
                with open(dialog.get_filename(), 'w') as fp:
                    fp.write(text)
        finally:
            dialog.destroy()
        return True

    def on_report_bug_button_activate_link(self, button):
        """
        Handle the click on report bug button

        :type button: Gtk.LinkButton
        """

        logger.info(bug_send)

        def xdg_email_exit_cb(codes):
            stdout, stderr, code = codes
            if code == 0:
                logger.info(bug_sent)
            elif code in BUG_REPORT_ERRORS:
                logger.error(bug_error, err=BUG_REPORT_ERRORS[code],
                             stderr=stderr, hide_to_user=True)
            else:
                logger.error(bug_report_fail, code=code, stderr=stderr,
                             hide_to_user=True)

        body = textwrap.dedent(
            f'''

            Please keep the following lines as they are.
            The attachment contains the logs of Virtualbricks.

            Virtualbricks version: {__version__}
            '''
        )
        messages = self._textbuffer.get_property('text')
        # Do not remove the file once xdg-email exits.
        fd, filename = tempfile.mkstemp(prefix='virtualbricks_log_', text=True)
        with os.fdopen(fd, mode='wt', encoding='utf8') as fp:
            fp.write(messages)
        params = [
            '--utf8', '--subject', '[Virtualbricks] ', '--body', body,
            '--attach', filename
        ]
        env = dict(os.environ, MM_NOTTTY='1')
        proc_d = utils.getProcessOutputAndValue('xdg-email', params, env)
        proc_d.addCallback(xdg_email_exit_cb)
        proc_d.addErrback(logger.failure_eb, bug_err_unknown)
        # Stop the propagation of activate-link signal
        return True
