# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

from twisted.internet import defer, task
from twisted.trial import unittest

from virtualbricks.console import ampwire
from virtualbricks.engine import LocalEngine
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import GdkPixbuf, Gtk

    from virtualbricks.gui.mainwindow import readme
    from virtualbricks.gui.mainwindow.readme import (
        GAP,
        MARGIN,
        SAVE_AFTER,
        SYNTAX,
        ReadmeTab,
    )
    from virtualbricks.gui.mainwindow.tab import FADED_OPACITY

README = "# OSPF lab\n\nThree **routers**."
RENDERED = "OSPF lab\nThree routers."


class TestReadmeTab(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def setUp(self):
        self.window = Gtk.OffscreenWindow()
        self.addCleanup(self.window.destroy)
        # the saves of the edits never come
        self.tab = ReadmeTab(LocalEngine(None), clock=task.Clock())
        # first: a popover in an offscreen window, unlike a real one, makes
        # GTK complain when the window goes
        self.addCleanup(self.tab.syntax_button.get_popover().destroy)
        self.window.add(self.tab)
        self.window.show()
        self.buffer = self.tab.editor.get_buffer()

    def showing(self):
        return self.tab.stack.get_visible_child_name()

    def rendered(self):
        preview = self.tab.preview.get_buffer()
        return preview.get_text(*preview.get_bounds(), False)

    def test_the_preview_first(self):
        self.assertTrue(self.tab.preview_button.get_active())
        self.assertFalse(self.tab.edit_button.get_active())
        self.assertEqual(self.showing(), "empty")
        self.assertTrue(self.tab.edit_button.get_visible())
        self.assertFalse(self.tab.preview_button.get_visible())
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
        # the pencil gives way to the eye and the syntax
        self.assertFalse(self.tab.edit_button.get_visible())
        self.assertTrue(self.tab.preview_button.get_visible())
        self.assertTrue(self.tab.syntax_button.get_visible())
        # rendered when the preview shows again
        self.buffer.set_text(README)
        self.assertEqual(self.rendered(), "")
        self.tab.preview_button.set_active(True)
        self.assertEqual(self.showing(), "preview")
        self.assertEqual(self.rendered(), RENDERED)
        self.assertTrue(self.tab.edit_button.get_visible())
        self.assertFalse(self.tab.preview_button.get_visible())
        self.assertFalse(self.tab.syntax_button.get_visible())

    def test_the_key_stays_on_the_buttons(self):
        self.tab.edit_button.set_active(True)
        # the eye pressed with a key, it hides
        self.tab.preview_button.grab_focus()
        self.tab.preview_button.set_active(True)
        self.assertIs(self.window.get_focus(), self.tab.edit_button)

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
        self.assertTrue(tab.edit_button.get_mapped())
        for button in (tab.preview_button, tab.syntax_button):
            self.assertFalse(button.get_mapped())
        tab.edit_button.set_active(True)
        self.assertFalse(tab.edit_button.get_mapped())
        for button in (tab.preview_button, tab.syntax_button):
            self.assertTrue(button.get_mapped())
        # an overlay gives each of its children a window: where in the tab
        x, y = tab.buttons.translate_coordinates(tab, 0, 0)
        self.assertEqual(y, GAP)
        width = tab.buttons.get_allocated_width()
        self.assertEqual(x + width + GAP, tab.get_allocated_width())

    def test_opaque_while_the_syntax_shows(self):
        buttons = self.tab.buttons
        self.assertAlmostEqual(buttons.get_opacity(), FADED_OPACITY, places=2)
        self.tab.edit_button.set_active(True)
        self.tab.syntax_button.set_active(True)
        self.assertEqual(buttons.get_opacity(), 1.0)
        self.tab.syntax_button.set_active(False)
        self.assertAlmostEqual(buttons.get_opacity(), FADED_OPACITY, places=2)

    def test_the_same_margin_on_each_side(self):
        # the text goes under the buttons, the editor's as the preview's
        self.tab.edit_button.set_active(True)
        self.tab.preview_button.set_active(True)
        for view in (self.tab.preview, self.tab.editor):
            margins = (
                view.get_left_margin(),
                view.get_right_margin(),
                view.get_top_margin(),
                view.get_bottom_margin(),
            )
            self.assertEqual(margins, (MARGIN,) * 4)
        label = self.tab.empty_label
        margins = (
            label.get_margin_start(),
            label.get_margin_end(),
            label.get_margin_top(),
            label.get_margin_bottom(),
        )
        self.assertEqual(margins, (MARGIN,) * 4)

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

    name = "lab"

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
        engine = LocalEngine(None, workspace=FakeWorkspace(self.project))
        self.tab = ReadmeTab(engine, self.clock)
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

    def test_a_load_that_fails(self):
        # over a connection lost: what shows stays
        self.tab.on_open()
        self.tab.engine.readme = lambda: defer.fail(
            ampwire.CommandFailed("The connection to lab is lost")
        )
        self.tab.on_shown()
        self.assertEqual(self.text(), README)

    def test_a_save_that_fails(self):
        # over a connection: the edits stay, for the next save
        logger = FakeLogger()
        self.patch(readme, "logger", logger)
        self.tab.engine.set_readme = lambda text: defer.fail(
            ampwire.CommandFailed("The connection to lab is lost")
        )
        self.tab.on_open()
        self.edit()
        self.tab.on_save()
        self.assertTrue(self.buffer.get_modified())
        self.assertEqual(
            logger.formatted(),
            ["Cannot save the README: The connection to lab is lost"],
        )

    def test_the_pictures_of_the_open_project(self):
        asked = []

        def picture(name, path):
            asked.append((name, path))
            pixbuf = GdkPixbuf.Pixbuf.new(
                GdkPixbuf.Colorspace.RGB, False, 8, 4, 3
            )
            return defer.succeed(pixbuf.save_to_bufferv("png", [], [])[1])

        self.tab.engine.picture = picture
        self.project.description = "![the map](map.png)"
        self.tab.on_open()
        self.assertEqual(asked, [("lab", "map.png")])
        [image] = self.tab.preview.get_children()
        self.assertEqual(image.get_accessible().get_name(), "the map")

    def test_no_project_open(self):
        self.tab.engine.workspace.current = None
        self.buffer.set_text("![the map](map.png)")
        textbuffer = self.tab.preview.get_buffer()
        self.assertEqual(
            textbuffer.get_text(*textbuffer.get_bounds(), False), "the map"
        )

    def test_nothing_to_save(self):
        self.tab.on_open()
        self.tab.on_save()
        self.tab.on_left()
        self.assertEqual(self.project.saved, [])
