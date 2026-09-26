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
The Readme tab: the preview, the editor, the buttons over them, and the
README it loads and saves.
"""

from twisted.internet import task
from twisted.trial import unittest

from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.mainwindow.readme import (
        GAP,
        SAVE_AFTER,
        SYNTAX,
        ReadmeTab,
    )

README = "# OSPF lab\n\nThree **routers**."
RENDERED = "OSPF lab\nThree routers."


class TestReadmeTab(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.window, self.tab = self.tab_in_window()
        self.buffer = self.tab.editor.get_buffer()

    def tab_in_window(self, css=None):
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        # the saves of the edits never come
        tab = ReadmeTab(clock=task.Clock())
        # first: a popover in an offscreen window, unlike a real one, makes
        # GTK complain when the window goes
        self.addCleanup(tab.syntax_button.get_popover().destroy)
        if css is not None:
            # an offscreen window doesn't take a new style once shown
            style = Gtk.CssProvider()
            style.load_from_data(css)
            tab.edit_button.get_style_context().add_provider(
                style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        window.add(tab)
        window.show()
        return window, tab

    def run_idle_calls(self):
        while Gtk.events_pending():
            Gtk.main_iteration()

    def showing(self):
        return self.tab.stack.get_visible_child_name()

    def rendered(self):
        preview = self.tab.preview.get_buffer()
        return preview.get_text(*preview.get_bounds(), False)

    def test_the_preview_first(self):
        self.assertTrue(self.tab.preview_button.get_active())
        self.assertFalse(self.tab.edit_button.get_active())
        self.assertEqual(self.showing(), "empty")
        self.assertFalse(self.tab.syntax_button.get_visible())

    def test_a_text_loaded_is_rendered(self):
        self.buffer.set_text(README)
        self.assertEqual(self.showing(), "preview")
        self.assertTrue(self.tab.preview.get_mapped())
        self.assertEqual(self.rendered(), RENDERED)
        # nothing to read
        self.buffer.set_text(" \n\n")
        self.assertEqual(self.showing(), "empty")
        self.assertTrue(self.tab.empty_label.get_mapped())

    def test_the_editor(self):
        self.tab.edit_button.set_active(True)
        self.assertEqual(self.showing(), "editor")
        self.assertTrue(self.tab.editor.get_mapped())
        self.assertIs(self.window.get_focus(), self.tab.editor)
        self.assertTrue(self.tab.syntax_button.get_visible())
        # rendered when the preview shows again
        self.buffer.set_text(README)
        self.assertEqual(self.rendered(), "")
        self.tab.preview_button.set_active(True)
        self.assertEqual(self.showing(), "preview")
        self.assertEqual(self.rendered(), RENDERED)
        self.assertFalse(self.tab.syntax_button.get_visible())

    def test_show_the_preview(self):
        self.tab.edit_button.set_active(True)
        self.buffer.set_text(README)
        self.tab.show_preview()
        self.assertTrue(self.tab.preview_button.get_active())
        self.assertEqual(self.rendered(), RENDERED)

    def test_the_buttons_say_what_they_do(self):
        tab = self.tab
        for button, icon, name in (
            (tab.edit_button, "document-edit-symbolic", "Edit"),
            (tab.preview_button, "view-reveal-symbolic", "Preview"),
            (tab.syntax_button, "dialog-question-symbolic", "Syntax"),
        ):
            self.assertEqual(button.get_image().get_icon_name()[0], icon)
            self.assertEqual(button.get_tooltip_text(), name)
            self.assertEqual(button.get_accessible().get_name(), name)

    def test_the_buttons_in_the_corner(self):
        tab = self.tab
        for button in (tab.edit_button, tab.preview_button):
            self.assertTrue(button.get_mapped())
        tab.edit_button.set_active(True)
        self.assertTrue(tab.syntax_button.get_mapped())
        # an overlay gives each of its children a window: where in the tab
        x, y = tab.buttons.translate_coordinates(tab, 0, 0)
        self.assertEqual(y, GAP)
        width = tab.buttons.get_allocated_width()
        self.assertEqual(x + width + GAP, tab.get_allocated_width())

    def test_no_text_under_the_buttons(self):
        _, width = self.tab.buttons.get_preferred_width()
        self.assertEqual(self.tab.preview.get_right_margin(), width)
        self.assertEqual(self.tab.empty_label.get_margin_end(), width)
        # three buttons over the editor
        self.tab.edit_button.set_active(True)
        _, wider = self.tab.buttons.get_preferred_width()
        self.assertGreater(wider, width)
        self.assertEqual(self.tab.editor.get_right_margin(), wider)

    def test_the_margin_follows_the_theme(self):
        before = ReadmeTab().preview.get_right_margin()
        _, tab = self.tab_in_window(b"button { padding-left: 40px; }")
        _, width = tab.buttons.get_preferred_width()
        self.assertGreater(width, before)
        # measured once the buttons have their room
        self.assertEqual(tab.preview.get_right_margin(), before)
        self.run_idle_calls()
        self.assertEqual(tab.preview.get_right_margin(), width)

    def test_not_measured_after_the_end(self):
        before = ReadmeTab().preview.get_right_margin()
        _, tab = self.tab_in_window(b"button { padding-left: 40px; }")
        tab.destroy()
        self.run_idle_calls()
        self.assertEqual(tab.preview.get_right_margin(), before)

    def test_the_syntax(self):
        popover = self.tab.syntax_button.get_popover()
        [grid] = popover.get_children()
        self.assertTrue(grid.get_visible())
        texts = [
            label.get_text()
            for label in grid.get_children()
            if label.get_visible()
        ]
        for source, meaning in SYNTAX:
            self.assertIn(source, texts)
            self.assertIn(meaning, texts)
        self.assertIn("Markdown", texts)
        self.assertIn("Anything else shows as you typed it.", texts)


class FakeProject:
    def __init__(self, description):
        self.description = description
        self.saved = []

    def get_description(self):
        return self.description

    def set_description(self, text):
        self.description = text
        self.saved.append(text)


class FakeWorkspace:
    def __init__(self, current):
        self.current = current


class TestLoadAndSave(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.project = FakeProject(README)
        self.clock = task.Clock()
        self.tab = ReadmeTab(FakeWorkspace(self.project), self.clock)
        self.addCleanup(self.tab.destroy)
        self.buffer = self.tab.editor.get_buffer()

    def text(self):
        return self.buffer.get_property("text")

    def edit(self, text=" More."):
        self.buffer.insert(self.buffer.get_end_iter(), text)

    def test_a_project_opens(self):
        self.tab.edit_button.set_active(True)
        self.tab.on_open()
        self.assertEqual(self.text(), README)
        # on the preview; loading isn't an edit
        self.assertTrue(self.tab.showing_preview())
        self.assertFalse(self.buffer.get_modified())
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_loaded_when_it_shows(self):
        self.tab.on_open()
        self.project.description = "Another"
        self.tab.on_shown()
        self.assertEqual(self.text(), "Another")

    def test_an_edit_is_saved_after_a_while(self):
        self.tab.on_open()
        self.edit()
        self.edit()
        # one save for both
        self.assertEqual(len(self.clock.getDelayedCalls()), 1)
        self.clock.advance(SAVE_AFTER - 1)
        self.assertEqual(self.project.saved, [])
        self.clock.advance(1)
        self.assertEqual(self.project.saved, [README + " More. More."])
        self.assertFalse(self.buffer.get_modified())

    def test_saved_at_once(self):
        for hook in ("on_left", "on_save", "on_quit"):
            self.project.saved.clear()
            self.edit()
            getattr(self.tab, hook)()
            self.assertEqual(self.project.saved, [self.text()], hook)
            # not twice
            self.assertEqual(self.clock.getDelayedCalls(), [], hook)

    def test_nothing_to_save(self):
        self.tab.on_open()
        self.tab.on_save()
        self.tab.on_left()
        self.assertEqual(self.project.saved, [])
