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
What the tabs of rows share, beyond what the Bricks tab's tests show: what
each kind says, the waiting dot, a kind found by name only, and the helpers.
"""

from twisted.internet import defer

from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import GdkPixbuf, Gio, GLib, Gtk

    from virtualbricks.gui.mainwindow import rowtab
    from virtualbricks.gui.mainwindow.rowtab import (
        Row,
        RowList,
        RowsTab,
        ThemeIcons,
        empty_icon,
        log_failures,
        theme_icon,
    )

    class Actions(Gio.SimpleActionGroup):
        updates = 0

        def update(self):
            self.updates += 1

    class EventRow(Row):
        """A row of an event, waiting while it is scheduled."""

        GROUP = "event"
        broken = False

        def make_actions(self):
            return Actions()

        def menu_model(self):
            return Gio.Menu()

        def update(self, processes=False):
            running = self.item.scheduled is not None
            self.show(
                "an event",
                "Waiting" if running else "Ready",
                running,
                self.broken,
                None,
                dot="waiting",
            )

    class EventList(RowList):
        def signals(self):
            factory = self.factory
            return (
                factory.event_added,
                factory.event_removed,
                factory.event_changed,
            )

        def items(self):
            return list(self.factory.events)

        def make_row(self, item):
            return EventRow(self.gui, item, self.icons, self._sizes)


class Scheduled:
    def cancel(self):
        pass


class RowTabTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.event = self.factory.new_event("start-vms")
        self.list = EventList(object(), self.factory)
        self.addCleanup(self.list.destroy)
        self.addCleanup(self.list.close)
        self.row = self.list.row_of(self.event)


class TestWhatEachKindSays(GuiTestCase):

    def test_the_hooks(self):
        for cls, names in (
            (Row, ("make_actions", "menu_model", "update")),
            (RowList, ("items",)),
            (
                RowsTab,
                (
                    "make_list",
                    "items",
                    "new",
                    "start_all",
                    "stop_all",
                ),
            ),
        ):
            for name in names:
                self.assertRaises(
                    NotImplementedError, getattr(cls, name), None
                )
        self.assertRaises(NotImplementedError, RowList.make_row, None, None)
        for name in (
            "count_text",
            "can_start",
            "panel_for",
            "settings_words",
        ):
            self.assertRaises(
                NotImplementedError, getattr(RowsTab, name), None, None
            )
        self.assertRaises(
            NotImplementedError, RowsTab.popup, None, None, None, None
        )
        self.assertRaises(
            NotImplementedError, Row.on_startstop_clicked, None, None
        )


class TestARow(RowTabTestCase):

    def test_waiting(self):
        self.event.scheduled = Scheduled()
        self.event.changed.notify(self.event)
        context = self.row.dot.get_style_context()
        self.assertTrue(context.has_class("waiting"))
        self.assertFalse(context.has_class("running"))
        rgba = context.get_property("background-color", Gtk.StateFlags.NORMAL)
        self.assertEqual(rgba.to_string(), "rgb(53,132,228)")
        self.assertEqual(self.row.state_label.get_text(), "Waiting")
        # and no more
        self.event.scheduled = None
        self.event.changed.notify(self.event)
        self.assertFalse(context.has_class("waiting"))

    def test_what_can_start(self):
        self.assertTrue(self.row.startstop.get_sensitive())
        self.row.broken = True
        self.row.update()
        self.assertFalse(self.row.startstop.get_sensitive())

    def test_its_actions(self):
        self.assertIs(self.row.get_action_group("event"), self.row.actions)
        updates = self.row.actions.updates
        self.row.update()
        self.assertEqual(self.row.actions.updates, updates + 1)

    def test_its_icon(self):
        # the event's, of the data folder
        pixbuf = self.row.icon.get_pixbuf()
        self.assertEqual(pixbuf.get_width(), rowtab.ICON_SIZE)


class TestAList(RowTabTestCase):

    def test_a_kind_found_by_name_only(self):
        self.assertEqual(self.list.kind(self.event), "")
        self.list.set_search("start")
        self.assertTrue(self.row.get_child_visible())
        # no kind to find
        self.list.set_search("event")
        self.assertFalse(self.row.get_child_visible())

    def test_rows_made_ready(self):
        # nothing to do, by default
        self.assertIsNone(self.list.prepare(self.row))

    def test_the_factory(self):
        other = self.factory.new_event("start-switches")
        self.assertEqual(
            [row.item for row in self.list.get_children()],
            [self.event, other],
        )
        self.factory.remove_event(self.event)
        self.assertEqual(
            [row.item for row in self.list.get_children()], [other]
        )


class TestTheHelpers(GuiTestCase):

    def test_log_failures(self):
        logger = FakeLogger()
        done = log_failures(
            [defer.succeed(1), defer.fail(RuntimeError("gone"))],
            "Not done.",
            logger,
        )
        self.successResultOf(done)
        self.assertEqual(logger.formatted(), ["Not done."])

    def test_the_empty_icon(self):
        pixbuf = empty_icon("event.png")
        self.assertEqual(
            (pixbuf.get_width(), pixbuf.get_height()),
            (rowtab.EMPTY_ICON_SIZE, rowtab.EMPTY_ICON_SIZE),
        )
        self.assertIsNone(empty_icon("nowhere.png"))


class FakeIconTheme:
    """An icon theme with red icons of some names."""

    def __init__(self, *names):
        self.names = names
        self.loaded = []

    def load_icon(self, name, size, flags):
        self.loaded.append((name, size))
        if name not in self.names:
            raise GLib.Error(f"no icon {name}")
        pixbuf = GdkPixbuf.Pixbuf.new(
            GdkPixbuf.Colorspace.RGB, False, 8, size, size
        )
        pixbuf.fill(0xFF000000)
        return pixbuf


def first_pixel(pixbuf):
    return tuple(pixbuf.get_pixels()[:3])


class TestThemeIcons(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.theme = FakeIconTheme("drive-harddisk")
        self.patch(Gtk.IconTheme, "get_default", lambda: self.theme)

    def test_the_first_that_the_theme_has(self):
        pixbuf = theme_icon(("disk-x", "drive-harddisk", "media-floppy"), 24)
        self.assertEqual(pixbuf.get_width(), 24)
        self.assertEqual(
            self.theme.loaded, [("disk-x", 24), ("drive-harddisk", 24)]
        )
        self.assertEqual(first_pixel(pixbuf), (255, 0, 0))

    def test_grey(self):
        pixbuf = theme_icon(("drive-harddisk",), 24, grey=True)
        red, green, blue = first_pixel(pixbuf)
        self.assertEqual(red, green)
        self.assertEqual(green, blue)

    def test_none(self):
        self.assertIsNone(theme_icon(("disk-x",), 24))

    def test_for_all_the_rows(self):
        icons = ThemeIcons(("drive-harddisk",), 24)
        self.assertEqual(first_pixel(icons.get(object(), True)), (255, 0, 0))
        grey = icons.get(object(), False)
        self.assertEqual(len(set(first_pixel(grey))), 1)
        # made once
        self.assertEqual(len(self.theme.loaded), 2)
