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
The Bricks tab: the row above the list, the page of a project without
bricks, the keys and the mouse.
"""

import os

from twisted.internet import defer

from virtualbricks.bricks.draft import Draft
from virtualbricks.engine import LocalEngine
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui.mainwindow import rowtab
    from virtualbricks.gui.mainwindow.bricks import brickmenu, tab
    from virtualbricks.gui.mainwindow.bricks.newbrick import NewBrickPopover
    from virtualbricks.gui.mainwindow.bricks.tab import BricksTab, count
    from virtualbricks.gui.mainwindow.rowtab import types
    from virtualbricks.gui.mainwindow.picture import Icons


class FakeProcess:
    pid = 41301


def packing(box):
    """How box packs its children: each child, whether it expands and fills."""

    return [
        (
            child,
            box.child_get_property(child, "expand"),
            box.child_get_property(child, "fill"),
        )
        for child in box.get_children()
    ]


class FakeSwitch:
    """A brick for the icons: a switch."""

    class config:
        icon = ""

    def get_type(self):
        return "Switch"


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.engine = LocalEngine(factory)
        self.window = object()
        self.removed = []
        self.configured = []
        self.tab = None

    def curtain_up(self, brick):
        self.configured.append(brick)

    def curtain_down(self):
        # the panels close the settings through the window
        self.tab.close_settings()

    def ask_remove_brick(self, brick):
        self.removed.append(brick)


class FakeDialog:
    def __init__(self, shown, factory):
        self.shown = shown
        self.factory = factory

    def show(self, parent):
        self.shown.append((self.factory, parent))


class FakePanel:
    """A panel on a draft of brick: what the tab asks of it."""

    def __init__(self, calls, brick):
        self.calls = calls
        self.draft = Draft(brick)
        self.widget = Gtk.Box()
        self.hidden = Gtk.Label(label="hidden")
        self.widget.add(self.hidden)
        self.rows = {}

    def connect_changed(self, callback):
        pass

    def commit(self):
        self.calls.append("commit")

    def running(self):
        return False


class BricksTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        os.makedirs(self.factory.runtime_dir)
        self.logger = FakeLogger()
        self.patch(tab, "logger", self.logger)
        self.gui = FakeGui(self.factory)
        self.done = []
        self.sw = self.brick("switch", "sw")
        self.tab = BricksTab(self.gui, self.factory)
        self.gui.tab = self.tab
        self.addCleanup(self.tab.destroy)
        # a test that quits says so
        self.addCleanup(lambda: self.tab.on_quit())

    def brick(self, kind, name):
        brick = self.factory.new_brick(kind, name)

        def start():
            self.done.append(("on", name))
            return defer.succeed(brick)

        def stop():
            self.done.append(("off", name))
            return defer.succeed(brick)

        brick.start = start
        brick.stop = stop
        return brick

    def running(self, brick):
        brick.proc = FakeProcess()
        brick.changed.notify(brick)
        return brick

    def select(self, brick):
        row = self.tab.list.row_of(brick)
        self.tab.list.select_row(row)
        return row

    def key(self, keyval, state=0, string=""):
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        event.key.keyval = keyval
        event.key.state = Gdk.ModifierType(state)
        event.key.string = string
        event.key.length = len(string)
        # where it happens, once the tab shows, and from what
        event.key.window = self.tab.get_window()
        seat = Gdk.Display.get_default().get_default_seat()
        event.set_device(seat.get_keyboard())
        return event

    def press(self, *args, **kwargs):
        # the event outlives its key, which points into it
        event = self.key(*args, **kwargs)
        return self.tab.on_list_key_press(self.tab.list, event.key)

    def show(self):
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        window.set_size_request(900, 400)
        window.add(self.tab)
        window.show()
        return window


class TestTheRowAboveTheList(BricksTestCase):

    def test_its_parts(self):
        tab = self.tab
        self.assertEqual(tab.title, "_Bricks")
        self.assertEqual(tab.new_button.get_label(), "New Brick")
        self.assertEqual(
            tab.new_button.get_image().get_icon_name()[0], "list-add-symbolic"
        )
        self.assertEqual(tab.search.get_placeholder_text(), "Search bricks")
        self.assertEqual(tab.all_button.get_label(), "All")
        self.assertEqual(tab.running_button.get_label(), "Running")
        self.assertIn(tab.running_button, tab.all_button.get_group())
        self.assertTrue(tab.all_button.get_active())
        for button in (tab.all_button, tab.running_button):
            self.assertFalse(button.get_mode())
        self.assertEqual(tab.start_button.get_label(), "Start All")
        self.assertEqual(tab.stop_button.get_label(), "Stop All")
        self.assertEqual(
            tab.start_button.get_image().get_icon_name()[0],
            "media-playback-start-symbolic",
        )
        self.assertEqual(
            tab.stop_button.get_image().get_icon_name()[0],
            "media-playback-stop-symbolic",
        )
        for group in (tab.all_button, tab.start_button):
            self.assertTrue(
                group.get_parent().get_style_context().has_class("linked")
            )
        self.assertTrue(tab.count.get_style_context().has_class("dim-label"))
        for button in (tab.new_button, tab.start_button, tab.stop_button):
            self.assertTrue(button.get_always_show_image())
        self.assertEqual(tab.search.get_width_chars(), 24)
        self.show()
        for widget in (
            tab.new_button,
            tab.search,
            tab.all_button,
            tab.running_button,
            tab.count,
            tab.start_button,
            tab.stop_button,
            tab.list,
        ):
            self.assertTrue(widget.is_drawable(), widget)
        self.assertEqual(tab.pages.get_visible_child_name(), "list")

    def test_how_it_is_made(self):
        tab = self.tab
        self.assertEqual(tab.get_children(), [tab.main_page])
        self.assertIs(tab.get_visible_child(), tab.main_page)
        header, separator, pages = tab.main_page.get_children()
        self.assertIsInstance(separator, Gtk.Separator)
        self.assertEqual(
            [
                (expand, fill)
                for _child, expand, fill in packing(tab.main_page)
            ],
            [(False, False), (False, False), (True, True)],
        )
        self.assertIs(pages, tab.pages)
        filters = tab.all_button.get_parent()
        all_bricks = tab.start_button.get_parent()
        self.assertEqual(
            packing(header),
            [
                (tab.new_button, False, False),
                (tab.search, False, False),
                (filters, False, False),
                (tab.count, False, False),
                (all_bricks, False, False),
            ],
        )
        # from the right: the buttons for all bricks, then the count
        self.assertEqual(
            [
                header.child_get_property(child, "pack-type")
                for child in header
            ],
            [Gtk.PackType.START] * 3 + [Gtk.PackType.END] * 2,
        )
        self.assertEqual(
            packing(filters),
            [
                (tab.all_button, False, False),
                (tab.running_button, False, False),
            ],
        )
        self.assertEqual(
            packing(all_bricks),
            [
                (tab.start_button, False, False),
                (tab.stop_button, False, False),
            ],
        )
        for widget in (header, separator, pages, filters, all_bricks):
            self.assertTrue(widget.get_visible(), widget)
        self.assertEqual(
            separator.get_orientation(), Gtk.Orientation.HORIZONTAL
        )
        empty = tab.empty
        self.assertEqual(
            [(expand, fill) for _child, expand, fill in packing(empty)],
            [(False, False)] * 3,
        )
        for child in empty.get_children():
            self.assertTrue(child.get_visible(), child)
        words = empty.get_children()[2]
        self.assertTrue(words.get_line_wrap())
        self.assertEqual(words.get_max_width_chars(), 40)

    def test_the_count(self):
        self.assertEqual(self.tab.count.get_text(), "0 of 1 running")
        vm = self.brick("qemu", "vm")
        self.assertEqual(self.tab.count.get_text(), "0 of 2 running")
        self.running(vm)
        self.assertEqual(self.tab.count.get_text(), "1 of 2 running")
        self.assertEqual(count([]), "0 of 0 running")

    def test_new_brick_under_its_button(self):
        opened = []
        self.patch(
            NewBrickPopover,
            "popup_at",
            lambda popover, widget: opened.append((popover, widget)),
        )
        self.tab.new_button.clicked()
        popover = self.tab.new_popover
        self.addCleanup(popover.destroy)
        # in a project without bricks too; the popover stays
        self.factory.remove_brick(self.sw)
        self.tab.new_button.clicked()
        self.assertEqual(opened, [(popover, self.tab.new_button)] * 2)

    def test_a_new_brick_shows_its_settings(self):
        self.patch(NewBrickPopover, "popup_at", lambda popover, widget: None)
        self.tab.new_button.clicked()
        popover = self.tab.new_popover
        self.addCleanup(popover.destroy)
        row = next(row for row in popover.rows if row.kind.type == "Tap")
        popover.on_row_activated(popover.list, row)
        tap = self.factory.get_brick("tap1")
        self.assertIsNotNone(tap)
        self.assertIs(self.tab.list.selected(), tap)
        self.assertEqual(self.gui.configured, [tap])

    def test_start_all_starts_what_can(self):
        self.brick("qemu", "vm")
        self.brick("tap", "tap")  # not connected
        self.running(self.brick("switch", "sw2"))
        self.tab.start_button.clicked()
        self.assertEqual(self.done, [("on", "sw"), ("on", "vm")])

    def test_stop_all_stops_what_runs(self):
        self.brick("qemu", "vm")
        self.running(self.sw)
        self.tab.stop_button.clicked()
        self.assertEqual(self.done, [("off", "sw")])

    def test_what_fails_is_logged(self):
        self.sw.start = lambda: defer.fail(RuntimeError("no vde_switch"))
        self.successResultOf(self.tab.start_all())
        vm = self.running(self.brick("qemu", "vm"))

        def fail():
            raise RuntimeError("gone")

        vm.stop = fail
        self.successResultOf(self.tab.stop_all())
        self.assertEqual(
            self.logger.formatted(),
            ["Brick not started.", "Brick not stopped."],
        )

    def test_the_buttons_for_all_bricks(self):
        tab = self.tab
        self.assertTrue(tab.start_button.get_sensitive())
        self.assertFalse(tab.stop_button.get_sensitive())
        self.running(self.sw)
        self.assertFalse(tab.start_button.get_sensitive())
        self.assertTrue(tab.stop_button.get_sensitive())
        # a tap that can't start
        self.brick("tap", "tap")
        self.assertFalse(tab.start_button.get_sensitive())

    def test_the_search(self):
        self.tab.search.set_text("vm")
        self.tab.search.emit("search-changed")
        self.assertEqual(self.tab.list.search, "vm")
        self.tab.search.emit("stop-search")
        self.assertEqual(self.tab.search.get_text(), "")
        self.assertEqual(self.tab.list.search, "")

    def test_the_running_bricks(self):
        self.tab.running_button.set_active(True)
        self.assertTrue(self.tab.list.only_running)
        self.tab.all_button.set_active(True)
        self.assertFalse(self.tab.list.only_running)


class TestAProjectWithoutBricks(BricksTestCase):

    def setUp(self):
        super().setUp()
        self.factory.remove_brick(self.sw)

    def test_the_page(self):
        tab = self.tab
        self.assertEqual(tab.pages.get_visible_child_name(), "empty")
        self.assertEqual(tab.count.get_text(), "")
        for widget in (
            tab.search,
            tab.all_button,
            tab.running_button,
            tab.start_button,
            tab.stop_button,
        ):
            self.assertFalse(widget.get_sensitive(), widget)
        self.assertTrue(tab.new_button.get_sensitive())
        # New Brick is the one above, where it always is
        image, title, words = tab.empty.get_children()
        self.assertEqual(title.get_text(), "No Bricks Yet")
        self.assertIn("A brick is a switch", words.get_text())
        self.assertTrue(words.get_style_context().has_class("dim-label"))
        pixbuf = image.get_pixbuf()
        self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (64, 64))
        self.assertAlmostEqual(image.get_opacity(), 0.35, places=2)
        # grey as a stopped brick in the Topology picture: not hatched
        self.assertEqual(
            pixbuf.get_pixels(),
            Icons(64).get(FakeSwitch(), False).get_pixels(),
        )
        # grey
        pixels, channels = pixbuf.get_pixels(), pixbuf.get_n_channels()
        for i in range(0, len(pixels) - channels, channels * 11):
            r, g, b = pixels[i : i + 3]
            self.assertTrue(abs(r - g) <= 1 and abs(g - b) <= 1, (r, g, b))

    def test_the_first_brick(self):
        self.brick("switch", "sw2")
        self.assertEqual(self.tab.pages.get_visible_child_name(), "list")
        self.assertTrue(self.tab.search.get_sensitive())

    def test_an_icon_not_there(self):
        self.patch(rowtab.graphics, "icon_file", lambda name: "/none")
        self.assertIsNone(rowtab.empty_icon("switch.png"))


class TestTheKeys(BricksTestCase):

    def test_delete(self):
        self.assertFalse(self.press(Gdk.KEY_Delete))
        self.select(self.sw)
        self.assertTrue(self.press(Gdk.KEY_Delete))
        self.assertTrue(self.press(Gdk.KEY_KP_Delete))
        self.assertEqual(self.gui.removed, [self.sw, self.sw])

    def test_delete_waits_while_it_runs(self):
        # as Delete… in its menu
        self.running(self.sw)
        self.select(self.sw)
        self.assertTrue(self.press(Gdk.KEY_Delete))
        self.assertEqual(self.gui.removed, [])

    def test_rename(self):
        shown = []
        self.patch(
            brickmenu,
            "RenameDialog",
            lambda factory, brick: FakeDialog(shown, brick),
        )
        self.assertFalse(self.press(Gdk.KEY_F2))
        self.select(self.sw)
        self.assertTrue(self.press(Gdk.KEY_F2))
        self.assertEqual(shown, [(self.sw, self.gui.window)])
        # not while it runs
        self.running(self.sw)
        self.assertTrue(self.press(Gdk.KEY_F2))
        self.assertEqual(len(shown), 1)

    def test_the_menu(self):
        shown = []
        self.patch(
            brickmenu,
            "popup",
            lambda *args: shown.append(args) or "menu",
        )
        self.assertTrue(self.press(Gdk.KEY_Menu))
        self.assertEqual(shown, [])
        row = self.select(self.sw)
        self.assertTrue(self.press(Gdk.KEY_Menu))
        self.assertTrue(self.press(Gdk.KEY_F10, Gdk.ModifierType.SHIFT_MASK))
        self.assertFalse(self.press(Gdk.KEY_F10))
        self.assertEqual(
            shown, [(row.menu_button, None, self.gui, self.sw, True)] * 2
        )
        self.assertEqual(self.tab._menu, "menu")

    def test_typing_searches(self):
        window = self.show()
        self.select(self.sw)
        self.tab.list.grab_focus()
        self.assertTrue(self.press(Gdk.KEY_v, string="v"))
        self.assertEqual(self.tab.search.get_text(), "v")
        self.assertIs(window.get_focus(), self.tab.search)
        # not a key that types
        self.assertFalse(self.press(Gdk.KEY_Up))

    def test_escape_clears_the_search(self):
        window = self.show()
        self.assertFalse(self.press(Gdk.KEY_Escape))
        self.tab.search.set_text("vm")
        self.assertTrue(self.press(Gdk.KEY_Escape))
        self.assertEqual(self.tab.search.get_text(), "")
        self.assertEqual(self.tab.list.search, "")
        # on the first brick, none selected
        self.assertIs(window.get_focus(), self.tab.list.row_of(self.sw))
        row = self.select(self.factory.new_brick("qemu", "vm"))
        self.tab.search.set_text("vm")
        self.assertTrue(self.press(Gdk.KEY_Escape))
        self.assertIs(window.get_focus(), row)

    def test_escape_without_bricks(self):
        self.factory.remove_brick(self.sw)
        self.tab.search.set_text("vm")
        self.tab.on_stop_search(self.tab.search)
        self.assertEqual(self.tab.search.get_text(), "")

    def test_what_types(self):
        for keyval, state, expected in (
            (Gdk.KEY_v, 0, True),
            (Gdk.KEY_V, Gdk.ModifierType.SHIFT_MASK, True),
            (Gdk.KEY_space, 0, True),
            (Gdk.KEY_v, Gdk.ModifierType.CONTROL_MASK, False),
            (Gdk.KEY_v, Gdk.ModifierType.MOD1_MASK, False),
            (Gdk.KEY_Up, 0, False),
            (Gdk.KEY_Return, 0, False),
        ):
            event = self.key(keyval, state)
            self.assertIs(types(event.key), expected, (keyval, state))

    def test_nothing_to_search(self):
        self.factory.remove_brick(self.sw)
        self.assertFalse(self.press(Gdk.KEY_v, string="v"))
        self.assertEqual(self.tab.search.get_text(), "")

    def test_control_f(self):
        window = self.show()
        event = self.key(Gdk.KEY_f, Gdk.ModifierType.CONTROL_MASK)
        self.assertTrue(self.tab.on_key_press(self.tab, event.key))
        self.assertIs(window.get_focus(), self.tab.search)
        event = self.key(Gdk.KEY_F, Gdk.ModifierType.CONTROL_MASK)
        self.assertTrue(self.tab.on_key_press(self.tab, event.key))
        event = self.key(Gdk.KEY_f)
        self.assertFalse(self.tab.on_key_press(self.tab, event.key))

    def test_the_signals(self):
        # the tab catches what the list leaves
        event = self.key(Gdk.KEY_f, Gdk.ModifierType.CONTROL_MASK)
        self.show()
        self.assertTrue(self.tab.emit("key-press-event", event))
        self.select(self.sw)
        self.assertTrue(
            self.tab.list.emit("key-press-event", self.key(Gdk.KEY_Delete))
        )
        self.assertEqual(self.gui.removed, [self.sw])


class TestTheMouse(BricksTestCase):

    def click(self, button, y):
        event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
        event.button.button = button
        event.button.y = y
        event.button.window = self.tab.list.get_window()
        return self.tab.list.emit("button-press-event", event)

    def test_the_right_button(self):
        shown = []
        self.patch(brickmenu, "popup", lambda *args: shown.append(args))
        # an OffscreenWindow allocates what it has when it shows
        self.brick("qemu", "vm")
        self.show()
        self.assertTrue(self.click(3, 70))
        self.assertIs(self.tab.list.selected(), list(self.factory.bricks)[1])
        self.assertIs(
            self.tab.get_toplevel().get_focus(),
            self.tab.list.row_of(list(self.factory.bricks)[1]),
        )
        [(widget, event, gui, brick, keys)] = shown
        self.assertIs(widget, self.tab.list)
        self.assertEqual(event.button, 3)
        self.assertEqual(
            (gui, brick, keys), (self.gui, list(self.factory.bricks)[1], True)
        )

    def test_not_on_a_brick(self):
        shown = []
        self.patch(brickmenu, "popup", lambda *args: shown.append(args))
        self.show()
        self.assertFalse(self.click(3, 390))
        self.assertFalse(self.click(1, 10))
        self.assertEqual(shown, [])

    def test_a_double_click_configures(self):
        row = self.tab.list.row_of(self.sw)
        self.tab.list.emit("row-activated", row)
        self.assertEqual(self.gui.configured, [self.sw])


class TestWhatTheWindowTells(BricksTestCase):

    def test_a_project_opens(self):
        self.tab.search.set_text("vm")
        self.tab.list.set_search("vm")
        self.tab.running_button.set_active(True)
        self.tab.on_open()
        self.assertEqual(self.tab.search.get_text(), "")
        self.assertEqual(self.tab.list.search, "")
        self.assertTrue(self.tab.all_button.get_active())
        self.assertFalse(self.tab.list.only_running)

    def test_quit(self):
        self.tab.on_quit()
        self.brick("qemu", "vm")
        self.assertEqual(self.tab.count.get_text(), "0 of 1 running")
        self.assertIsNone(self.tab.list.row_of(list(self.factory.bricks)[1]))
        self.tab.on_quit = lambda: None


class TestTheSettings(BricksTestCase):

    def fake_panels(self):
        calls = []
        controllers = {}

        def adapt(brick, gui):
            controllers[brick] = FakePanel(calls, brick)
            return controllers[brick]

        self.patch(tab, "new_panel", adapt)
        return calls, controllers

    def test_a_switch(self):
        window = self.show()
        tab = self.tab
        tab.configure(self.sw)
        self.assertIs(tab.configuring, self.sw)
        self.assertIs(tab.get_visible_child(), tab.settings)
        head, bar, _sep, scrolled, _sep2, actions = tab.settings.get_children()
        image, text = head.get_children()
        name, kind = text.get_children()
        self.assertEqual(name.get_text(), "sw")
        self.assertEqual(kind.get_text(), "Switch settings")
        self.assertTrue(kind.get_style_context().has_class("dim-label"))
        self.assertIs(image.get_pixbuf(), tab.list.icons.get(self.sw, False))
        # a panel on a draft, and the bar of a running switch, hidden
        [panel] = scrolled.get_child().get_child().get_children()
        self.assertIs(panel, tab._controller.widget)
        self.assertIs(bar, tab.running_bar)
        self.assertFalse(bar.get_visible())
        tab._controller.form.rows["ports"].control.set_value(8)
        self.assertEqual(self.sw.config.ports, 32)
        tab.ok_button.clicked()
        self.assertEqual(self.sw.config.ports, 8)
        self.assertIsNone(tab.configuring)
        self.assertIsNone(tab.settings)
        self.assertIs(tab.get_visible_child(), tab.main_page)
        # back on the brick
        row = tab.list.row_of(self.sw)
        self.assertIs(tab.list.get_selected_row(), row)
        self.assertIs(window.get_focus(), row)

    def test_cancel(self):
        self.tab.configure(self.sw)
        self.tab._controller.form.rows["ports"].control.set_value(8)
        self.tab.cancel_button.clicked()
        self.assertEqual(self.sw.config.ports, 32)
        self.assertIs(self.tab.get_visible_child(), self.tab.main_page)

    def test_the_page_of_a_draft(self):
        self.tab.configure(self.sw)
        page = self.tab.settings
        head, bar, _sep, scrolled, _sep2, actions = page.get_children()
        self.assertEqual(
            [(expand, fill) for _child, expand, fill in packing(page)],
            [(False, False)] * 3 + [(True, True)] + [(False, False)] * 2,
        )
        self.assertIs(bar, self.tab.running_bar)
        self.assertEqual(bar.get_message_type(), Gtk.MessageType.INFO)
        [words] = bar.get_content_area().get_children()
        self.assertIs(words, self.tab.running_words)
        why = self.tab.why
        # the first error, between Cancel and OK
        for child, expand, pack in (
            (self.tab.cancel_button, False, Gtk.PackType.START),
            (self.tab.ok_button, False, Gtk.PackType.END),
            (why, True, Gtk.PackType.END),
        ):
            self.assertIs(child.get_parent(), actions)
            self.assertEqual(
                actions.child_get_property(child, "expand"), expand
            )
            self.assertEqual(
                actions.child_get_property(child, "pack-type"), pack
            )
        self.assertLess(
            actions.child_get_property(self.tab.ok_button, "position"),
            actions.child_get_property(why, "position"),
        )
        self.assertTrue(why.get_style_context().has_class("error"))
        self.assertFalse(why.get_visible())
        self.assertTrue(self.tab.ok_button.get_sensitive())

    def test_ok_waits_for_the_errors(self):
        self.tab.configure(self.sw)
        panel = self.tab._controller
        panel.draft.set("ports", 200)
        panel.on_changed()
        self.assertFalse(self.tab.ok_button.get_sensitive())
        self.assertTrue(self.tab.why.get_visible())
        self.assertEqual(
            self.tab.why.get_text(), "Ports: 200 is outside 1–128"
        )
        # a setting without a row
        panel.draft.set("ports", 16)
        panel.draft.set("icon", 1)
        panel.on_changed()
        self.assertEqual(self.tab.why.get_text(), "1 is not a string")
        panel.draft.set("icon", "")
        panel.on_changed()
        self.assertTrue(self.tab.ok_button.get_sensitive())
        self.assertFalse(self.tab.why.get_visible())
        self.tab.ok_button.clicked()
        self.assertEqual(self.sw.config.ports, 16)
        self.assertIsNone(self.tab.configuring)

    def test_a_running_switch(self):
        self.running(self.sw)
        self.tab.configure(self.sw)
        self.assertTrue(self.tab.running_bar.get_visible())
        self.assertEqual(
            self.tab.running_words.get_text(),
            "sw is running. These change at once: Ports, Hub mode, Fast"
            " spanning tree.",
        )
        # it stops, and starts again, while its settings show
        self.sw.proc = None
        self.sw.changed.notify(self.sw)
        self.assertFalse(self.tab.running_bar.get_visible())
        self.running(self.sw)
        self.assertTrue(self.tab.running_bar.get_visible())
        # another brick doesn't count
        self.running(self.brick("switch", "sw2"))
        self.sw.proc = None
        sw3 = self.brick("switch", "sw3")
        sw3.changed.notify(sw3)
        self.assertTrue(self.tab.running_bar.get_visible())

    def test_closed(self):
        self.tab.configure(self.sw)
        self.tab.cancel_button.clicked()
        self.assertIsNone(self.tab.running_bar)
        self.assertIsNone(self.tab.running_words)
        self.assertIsNone(self.tab.why)
        # its changes, with nothing to show
        self.running(self.sw)

    def test_how_the_page_is_made(self):
        calls, controllers = self.fake_panels()
        self.tab.configure(self.sw)
        page = self.tab.settings
        self.assertEqual(
            [(expand, fill) for _child, expand, fill in packing(page)],
            [(False, False)] * 3 + [(True, True)] + [(False, False)] * 2,
        )
        # all of it but the bar of a running brick
        for child in page.get_children():
            visible = child is not self.tab.running_bar
            self.assertEqual(child.get_visible(), visible, child)
        head = page.get_children()[0]
        image, text = head.get_children()
        name, kind = text.get_children()
        self.assertEqual(
            packing(head), [(image, False, False), (text, True, True)]
        )
        self.assertEqual(
            packing(text), [(name, False, False), (kind, False, False)]
        )
        for widget in (image, text, name, kind):
            self.assertTrue(widget.get_visible(), widget)
        actions = page.get_children()[5]
        self.assertEqual(
            packing(actions),
            [
                (self.tab.cancel_button, False, False),
                (self.tab.why, True, True),
                (self.tab.ok_button, False, False),
            ],
        )
        self.assertEqual(self.tab.cancel_button.get_label(), "_Cancel")
        self.assertEqual(self.tab.ok_button.get_label(), "_OK")
        self.assertTrue(self.tab.ok_button.get_use_underline())
        self.assertTrue(
            self.tab.ok_button.get_style_context().has_class(
                "suggested-action"
            )
        )
        for button in (self.tab.cancel_button, self.tab.ok_button):
            self.assertTrue(button.get_visible())
        controller = controllers[self.sw]
        # the panel shows, but not what it hides
        self.assertTrue(controller.widget.get_visible())
        self.assertFalse(controller.hidden.get_visible())
        holder = controller.widget.get_parent()
        self.assertEqual(packing(holder), [(controller.widget, True, True)])
        self.assertEqual(
            (
                holder.get_margin_start(),
                holder.get_margin_end(),
                holder.get_margin_top(),
            ),
            (8, 8, 8),
        )
        self.assertTrue(holder.get_visible())

    def test_ok_takes_what_is_typed(self):
        calls, controllers = self.fake_panels()
        self.tab.configure(self.sw)
        self.tab.ok_button.clicked()
        self.assertEqual(calls, ["commit"])
        self.assertIsNone(self.tab.configuring)
        # Cancel doesn't
        self.tab.configure(self.sw)
        self.tab.cancel_button.clicked()
        self.assertEqual(calls, ["commit"])
        self.assertIsNone(self.tab.configuring)

    def test_a_number_typed(self):
        # and not yet taken by the spin button, as with Alt+O
        self.tab.configure(self.sw)
        self.tab._controller.form.rows["ports"].control.set_text("8")
        self.tab.ok_button.clicked()
        self.assertEqual(self.sw.config.ports, 8)

    def test_an_error_taken_at_ok(self):
        self.tab.configure(self.sw)
        spin = self.tab._controller.form.rows["ports"].control
        # beyond the limit of the spin button, as a value already in the file
        spin.set_range(1, 500)
        spin.set_text("200")
        # not through the button, which would hide an exception
        self.tab.on_ok_clicked(self.tab.ok_button)
        self.assertIs(self.tab.configuring, self.sw)
        self.assertEqual(self.sw.config.ports, 32)
        self.assertFalse(self.tab.ok_button.get_sensitive())
        self.assertEqual(
            self.tab.why.get_text(), "Ports: 200 is outside 1–128"
        )

    def test_escape(self):
        calls, controllers = self.fake_panels()
        self.tab.configure(self.sw)
        page = self.tab.settings
        event = self.key(Gdk.KEY_a)
        self.assertFalse(self.tab.on_settings_key_press(page, event.key))
        event = self.key(Gdk.KEY_Escape)
        self.assertTrue(self.tab.on_settings_key_press(page, event.key))
        self.assertIsNone(self.tab.configuring)
        # the page's key
        self.show()
        self.tab.configure(self.sw)
        self.assertTrue(
            self.tab.settings.emit("key-press-event", self.key(Gdk.KEY_Escape))
        )
        self.assertIsNone(self.tab.configuring)

    def test_another_brick(self):
        calls, controllers = self.fake_panels()
        vm = self.brick("qemu", "vm")
        self.tab.configure(self.sw)
        first = self.tab.settings
        self.tab.configure(vm)
        self.assertEqual(controllers[vm].draft.brick, vm)
        self.assertIs(self.tab.configuring, vm)
        self.assertIsNot(self.tab.settings, first)
        self.assertEqual(
            self.tab.get_children(), [self.tab.main_page, self.tab.settings]
        )

    def test_the_brick_deleted(self):
        calls, controllers = self.fake_panels()
        vm = self.brick("qemu", "vm")
        self.tab.configure(self.sw)
        self.factory.remove_brick(vm)
        self.assertIs(self.tab.configuring, self.sw)
        self.factory.remove_brick(self.sw)
        self.assertIsNone(self.tab.configuring)

    def test_another_project(self):
        calls, controllers = self.fake_panels()
        self.tab.configure(self.sw)
        self.tab.on_open()
        self.assertIsNone(self.tab.configuring)
        # and with none
        self.tab.on_open()

    def test_a_router_has_no_panel(self):
        self.tab.configure(self.brick("router", "r"))
        self.assertIsNone(self.tab.configuring)
        self.assertIs(self.tab.get_visible_child(), self.tab.main_page)

    def test_the_keys_of_the_list_wait(self):
        window = self.show()
        self.tab.configure(self.sw)
        event = self.key(Gdk.KEY_f, Gdk.ModifierType.CONTROL_MASK)
        self.assertFalse(self.tab.on_key_press(self.tab, event.key))
        self.assertIsNot(window.get_focus(), self.tab.search)

    def test_nothing_to_close(self):
        self.tab.close_settings()
        self.assertIs(self.tab.get_visible_child(), self.tab.main_page)

    def test_a_brick_gone_from_the_list(self):
        # the list follows the factory first
        calls, controllers = self.fake_panels()
        self.tab.configure(self.sw)
        self.tab.list.on_removed(self.sw)
        self.tab.close_settings()
        self.assertIsNone(self.tab.list.get_selected_row())

    def test_quit(self):
        calls, controllers = self.fake_panels()
        self.tab.on_quit()
        self.tab.on_quit = lambda: None
        self.tab.configure(self.sw)
        self.factory.remove_brick(self.sw)
        # not told any more
        self.assertIs(self.tab.configuring, self.sw)
