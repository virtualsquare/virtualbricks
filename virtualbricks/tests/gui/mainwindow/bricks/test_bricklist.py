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
The list of the Bricks tab: a row per brick, what it says, the search, the
running bricks, and a brick dropped on another.
"""

import os

from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, GObject, Gtk

    from virtualbricks.gui.mainwindow import rowtab
    from virtualbricks.gui.mainwindow.bricks.bricklist import (
        BrickList,
        BrickRow,
    )


def run_idle_calls():
    while Gtk.events_pending():
        Gtk.main_iteration()


class FakeProcess:
    pid = 41301


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.window = None
        self.started = []

    def startstop_brick(self, brick):
        self.started.append(brick)


class FakeDrag:
    """What the list asks GTK during a drag, and what it tells it."""

    def __init__(self, test, source):
        self.source = source
        self.statuses = []
        self.finished = []
        self.icons = []
        test.patch(Gtk, "drag_get_source_widget", lambda context: self.source)
        test.patch(Gdk, "drag_status", self.status)
        test.patch(Gtk, "drag_finish", self.finish)
        test.patch(Gtk, "drag_set_icon_widget", self.set_icon)

    def status(self, context, action, time):
        self.statuses.append((action, time))

    def finish(self, context, success, delete, time):
        self.finished.append((success, delete, time))

    def set_icon(self, context, widget, x, y):
        self.icons.append(widget)


class BrickListTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        os.makedirs(self.factory.runtime_dir)
        self.gui = FakeGui(self.factory)
        self.sw = self.factory.new_brick("switch", "sw")
        self.tap = self.factory.new_brick("tap", "tap")
        self.list = BrickList(self.gui, self.factory)
        self.addCleanup(self.list.destroy)
        # a test that closes it says so
        self.addCleanup(lambda: self.list.close())

    def brick(self, kind, name):
        return self.factory.new_brick(kind, name)

    def running(self, brick):
        brick.proc = FakeProcess()
        brick.notify_changed()
        return brick

    def row(self, brick):
        return self.list.row_of(brick)

    def rows(self):
        return [row.item for row in self.list.get_children()]

    def shown(self):
        return [
            row.item
            for row in self.list.get_children()
            if isinstance(row, BrickRow) and row.get_child_visible()
        ]


class TestTheRows(BrickListTestCase):

    def test_in_the_order_they_were_made(self):
        vm = self.brick("qemu", "vm")
        self.assertEqual(self.rows(), [self.sw, self.tap, vm])
        self.factory.del_brick(self.tap)
        self.assertEqual(self.rows(), [self.sw, vm])
        self.assertIsNone(self.row(self.tap))

    def test_a_brick_removed_unplugs_the_others(self):
        # the factory doesn't tell the tap
        self.tap.connect(self.sw.socks[0])
        self.factory.del_brick(self.sw)
        self.assertEqual(
            self.row(self.tap).state_label.get_text(), "Not connected"
        )

    def test_not_after_close(self):
        self.list.close()
        self.brick("qemu", "vm")
        self.factory.del_brick(self.tap)
        self.sw.config.ports = 8
        self.sw.notify_changed()
        self.assertEqual(self.rows(), [self.sw, self.tap])
        self.assertEqual(
            self.row(self.sw).detail.get_text(), "Switch · 32 ports"
        )
        # closed once
        self.list.close = lambda: None

    def test_its_parts(self):
        self.assertTrue(self.list.get_visible())
        self.assertFalse(self.list.get_activate_on_single_click())
        self.assertEqual(
            self.list.get_selection_mode(), Gtk.SelectionMode.SINGLE
        )
        self.assertIs(self.list.placeholder.get_parent(), self.list)
        self.assertTrue(self.list.placeholder.get_visible())
        self.assertTrue(
            self.list.placeholder.get_style_context().has_class("dim-label")
        )
        self.assertEqual(self.list.placeholder.get_text(), "No bricks")
        row = self.row(self.sw)
        [box] = row.get_children()
        text = box.get_children()[1]
        self.assertEqual(
            box.get_children(),
            [row.icon, text, row.state, row.startstop, row.menu_button],
        )
        self.assertEqual(text.get_children(), [row.name, row.detail])
        self.assertEqual(
            row.state.get_children(), [row.dot, row.warning, row.state_label]
        )
        # only the text takes the room left
        for child in box.get_children():
            expand = box.child_get_property(child, "expand")
            fill = box.child_get_property(child, "fill")
            self.assertEqual((expand, fill), (child is text, child is text))
        for widget in (
            row,
            box,
            row.icon,
            text,
            row.name,
            row.detail,
            row.state,
            row.state_label,
            row.startstop,
            row.menu_button,
        ):
            self.assertTrue(widget.get_visible(), widget)
        self.assertTrue(row.detail.get_style_context().has_class("dim-label"))
        # the states line up
        self.assertEqual(
            set(self.list._sizes.get_widgets()),
            {self.row(self.sw).state, self.row(self.tap).state},
        )

    def test_the_colours_of_the_state(self):
        row = self.row(self.running(self.sw))
        rgba = row.dot.get_style_context().get_property(
            "background-color", Gtk.StateFlags.NORMAL
        )
        self.assertEqual(rgba.to_string(), "rgb(51,209,122)")
        rgba = (
            self.row(self.tap)
            .warning.get_style_context()
            .get_property("color", Gtk.StateFlags.NORMAL)
        )
        self.assertEqual(rgba.to_string(), "rgb(229,165,10)")

    def test_what_a_row_says(self):
        row = self.row(self.sw)
        self.assertEqual(row.name.get_text(), "sw")
        self.assertEqual(row.detail.get_text(), "Switch · 32 ports")
        self.assertEqual(row.detail.get_tooltip_text(), "Switch · 32 ports")
        self.assertEqual(row.state_label.get_text(), "Stopped")
        self.assertIsNone(row.state.get_tooltip_text())
        self.assertEqual(row.menu_button.get_tooltip_text(), "Menu of sw")

    def test_a_router_says_its_kind(self):
        router = self.brick("router", "r")
        self.assertEqual(self.row(router).detail.get_text(), "Router")

    def test_a_change_of_one_brick_shows_in_the_others(self):
        self.tap.connect(self.sw.socks[0])
        self.assertEqual(
            self.row(self.tap).detail.get_text(), "Tap · on sw · no address"
        )
        self.factory.rename_item(self.sw, "sw1")
        self.assertEqual(
            self.row(self.tap).detail.get_text(), "Tap · on sw1 · no address"
        )
        self.assertEqual(self.row(self.sw).name.get_text(), "sw1")

    def test_the_icon(self):
        row = self.row(self.sw)
        pixbuf = row.icon.get_pixbuf()
        self.assertEqual(
            (pixbuf.get_width(), pixbuf.get_height()),
            (32, 32),
        )
        # GTK keeps 8 bits of it
        self.assertAlmostEqual(
            row.icon.get_opacity(), rowtab.STOPPED_OPACITY, places=2
        )
        self.assertIsNot(row.icon.get_pixbuf(), None)
        self.running(self.sw)
        self.assertEqual(row.icon.get_opacity(), 1.0)
        self.assertIsNot(row.icon.get_pixbuf(), pixbuf)

    def test_an_icon_not_there(self):
        vm = self.brick("qemu", "vm")
        vm.config.icon = "/nowhere.png"
        vm.notify_changed()
        row = self.row(vm)
        self.assertIsNone(row.icon.get_pixbuf())
        self.assertEqual(row.icon.get_icon_name()[0], "image-missing")

    def test_a_row_for_a_running_brick(self):
        # its summary, unless the list shows only what runs
        row = BrickRow(
            self.gui, self.running(self.sw), self.list.icons, Gtk.SizeGroup()
        )
        self.addCleanup(row.destroy)
        self.assertEqual(row.detail.get_text(), "Switch · 32 ports")

    def test_a_running_brick(self):
        row = self.row(self.running(self.sw))
        self.assertEqual(row.state_label.get_text(), "Running")
        self.assertEqual(row.state.get_tooltip_text(), "Process 41301")
        self.assertTrue(row.dot.get_visible())
        self.assertFalse(row.warning.get_visible())
        self.assertTrue(row.dot.get_style_context().has_class("running"))
        self.assertEqual(
            row.startstop.get_image().get_icon_name()[0],
            "media-playback-stop-symbolic",
        )
        self.assertEqual(row.startstop.get_tooltip_text(), "Stop sw")
        self.assertTrue(row.startstop.get_sensitive())
        # what the menu allows follows
        self.assertFalse(row.actions.get_action_enabled("rename"))

    def test_a_stopped_brick(self):
        row = self.row(self.sw)
        self.assertTrue(row.dot.get_visible())
        self.assertFalse(row.dot.get_style_context().has_class("running"))
        self.assertEqual(
            row.startstop.get_image().get_icon_name()[0],
            "media-playback-start-symbolic",
        )
        self.assertEqual(row.startstop.get_tooltip_text(), "Start sw")
        self.assertTrue(row.startstop.get_sensitive())
        self.running(self.sw)
        self.sw.proc = None
        self.sw.notify_changed()
        self.assertFalse(row.dot.get_style_context().has_class("running"))

    def test_a_brick_not_connected(self):
        row = self.row(self.tap)
        self.assertEqual(row.state_label.get_text(), "Not connected")
        self.assertEqual(row.state.get_tooltip_text(), "Connect tap first")
        self.assertFalse(row.dot.get_visible())
        self.assertTrue(row.warning.get_visible())
        self.assertFalse(row.startstop.get_sensitive())

    def test_a_brick_not_configured(self):
        capture = self.brick("capture", "cap")
        capture.connect(self.sw.socks[0])
        row = self.row(capture)
        self.assertEqual(row.state_label.get_text(), "Not configured")
        self.assertEqual(row.state.get_tooltip_text(), "Configure cap first")
        self.assertTrue(row.warning.get_visible())
        self.assertFalse(row.startstop.get_sensitive())

    def test_start_and_stop(self):
        self.row(self.sw).startstop.clicked()
        self.assertEqual(self.gui.started, [self.sw])

    def test_the_actions_of_the_menu(self):
        row = self.row(self.sw)
        self.assertIs(row.get_action_group("brick"), row.actions)
        self.assertIs(row.actions.brick, self.sw)

    def test_the_menu(self):
        row = self.row(self.sw)
        row.menu_button.clicked()
        popover = row.popover
        self.assertIsInstance(popover, Gtk.Popover)
        self.assertIs(popover.get_relative_to(), row.menu_button)
        self.assertTrue(popover.get_visible())
        # made when it opens: the tap can plug into the switch now
        self.tap.connect(self.sw.socks[0])
        destroyed = []
        popover.connect("destroy", destroyed.append)
        popover.popdown()
        popover.emit("closed")
        self.assertIsNone(row.popover)
        # later: GTK still uses it after "closed"
        self.assertEqual(destroyed, [])
        run_idle_calls()
        self.assertEqual(destroyed, [popover])
        opened = row.open_menu()
        self.assertIs(opened, row.popover)
        self.assertIsNot(opened, popover)
        row.popover.emit("closed")
        run_idle_calls()

    def test_the_selected_brick(self):
        self.assertIsNone(self.list.selected())
        self.list.select_row(self.row(self.tap))
        self.assertIs(self.list.selected(), self.tap)


class TestWhatTheListShows(BrickListTestCase):

    def setUp(self):
        super().setUp()
        self.vm = self.brick("qemu", "vm")
        self.running(self.sw)

    def test_everything(self):
        self.assertEqual(self.shown(), [self.sw, self.tap, self.vm])

    def test_a_search(self):
        self.list.set_search("TA")
        self.assertEqual(self.shown(), [self.tap])
        # by kind too
        self.list.set_search(" virtual ")
        self.assertEqual(self.shown(), [self.vm])
        self.list.set_search("zz")
        self.assertEqual(self.shown(), [])
        self.assertEqual(
            self.list.placeholder.get_text(), "No brick matches “zz”"
        )

    def test_the_running_bricks(self):
        self.list.set_only_running(True)
        self.assertEqual(self.shown(), [self.sw])
        self.assertEqual(
            self.row(self.sw).detail.get_text(), "Switch · process 41301"
        )
        # a stopped brick keeps its summary
        self.assertEqual(
            self.row(self.vm).detail.get_text(),
            "Virtual machine · i386 · 64 MiB · no network card",
        )
        self.running(self.vm)
        self.assertEqual(self.shown(), [self.sw, self.vm])
        self.list.set_only_running(False)
        self.assertEqual(
            self.row(self.sw).detail.get_text(), "Switch · 32 ports"
        )

    def test_what_the_list_says_when_it_is_empty(self):
        self.assertEqual(self.list.placeholder.get_text(), "No bricks")
        self.list.set_only_running(True)
        self.assertEqual(
            self.list.placeholder.get_text(), "No brick is running"
        )
        self.list.set_search("tap")
        self.assertEqual(
            self.list.placeholder.get_text(), "No running brick matches “tap”"
        )
        self.list.set_search("")
        self.assertEqual(
            self.list.placeholder.get_text(), "No brick is running"
        )


class TestDragAndDrop(BrickListTestCase):

    def setUp(self):
        super().setUp()
        self.drag = FakeDrag(self, self.row(self.tap))

    def test_every_row_drags_and_takes_bricks(self):
        target = Gdk.Atom.intern("virtualbricks/brick", False)
        for row in self.list.get_children():
            for targets in (
                row.drag_source_get_target_list(),
                row.drag_dest_get_target_list(),
            ):
                found, _info = targets.find(target)
                self.assertTrue(found)

    def test_the_icon_of_the_drag(self):
        row = self.row(self.tap)
        self.list.on_drag_begin(row, None)
        [icon] = self.drag.icons
        image, label = icon.get_children()
        self.assertIs(label, self.list._drag_label)
        self.assertEqual(label.get_text(), "tap")
        pixbuf = image.get_pixbuf()
        self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (24, 24))
        for widget in (icon, image, label):
            self.assertTrue(widget.get_visible())
        self.assertAlmostEqual(row.get_opacity(), 0.45, places=2)
        destroyed = []
        icon.connect("destroy", destroyed.append)
        self.list.on_drag_end(row, None)
        self.assertEqual(row.get_opacity(), 1.0)
        self.assertIsNone(self.list._drag_label)
        self.assertEqual(destroyed, [icon])
        # and once more, without a drag
        self.list.on_drag_end(row, None)

    def test_the_icon_of_a_brick_without_one(self):
        vm = self.brick("qemu", "vm")
        vm.config.icon = "/nowhere.png"
        vm.notify_changed()
        self.list.on_drag_begin(self.row(vm), None)
        image, label = self.drag.icons[0].get_children()
        self.assertIsNone(image.get_pixbuf())

    def motion(self, row):
        highlights = []
        row.drag_highlight = lambda: highlights.append("on")
        row.drag_unhighlight = lambda: highlights.append("off")
        self.assertTrue(self.list.on_drag_motion(row, None, 1, 2, 42))
        return highlights

    def test_over_a_brick_that_takes_it(self):
        self.list.on_drag_begin(self.row(self.tap), None)
        self.assertEqual(self.motion(self.row(self.sw)), ["on"])
        self.assertEqual(self.drag.statuses, [(Gdk.DragAction.LINK, 42)])
        self.assertEqual(self.list._drag_label.get_text(), "Connect tap to sw")
        highlights = []
        self.row(self.sw).drag_unhighlight = lambda: highlights.append("off")
        self.list.on_drag_leave(self.row(self.sw), None, 43)
        self.assertEqual(highlights, ["off"])
        self.assertEqual(self.list._drag_label.get_text(), "tap")

    def test_over_a_brick_that_doesnt(self):
        tap2 = self.brick("tap", "tap2")
        self.list.on_drag_begin(self.row(self.tap), None)
        self.motion(self.row(self.sw))
        self.assertEqual(self.motion(self.row(tap2)), ["off"])
        self.assertEqual(self.drag.statuses[-1], (Gdk.DragAction(0), 42))
        self.assertEqual(self.list._drag_label.get_text(), "tap")

    def test_not_a_brick(self):
        self.drag.source = Gtk.Button()
        row = self.row(self.sw)
        self.assertIs(self.list.on_drag_motion(row, None, 1, 2, 42), False)
        self.list.on_drag_leave(row, None, 43)
        self.assertTrue(self.list.on_drag_drop(row, None, 1, 2, 44))
        self.assertEqual(self.drag.finished, [(False, False, 44)])

    def test_the_drop(self):
        self.assertTrue(
            self.list.on_drag_drop(self.row(self.sw), None, 1, 2, 44)
        )
        self.assertIs(self.tap.plugs[0].sock, self.sw.socks[0])
        self.assertEqual(self.drag.finished, [(True, False, 44)])

    def test_a_drop_that_connects_nothing(self):
        tap2 = self.brick("tap", "tap2")
        self.assertTrue(self.list.on_drag_drop(self.row(tap2), None, 1, 2, 44))
        self.assertIsNone(self.tap.plugs[0].sock)
        self.assertEqual(self.drag.finished, [(False, False, 44)])

    def test_the_signals(self):
        row = self.row(self.sw)
        for signal in (
            "drag-begin",
            "drag-end",
            "drag-motion",
            "drag-leave",
            "drag-drop",
        ):
            signal_id = GObject.signal_lookup(signal, Gtk.Widget)
            self.assertTrue(
                GObject.signal_has_handler_pending(row, signal_id, 0, True),
                signal,
            )
