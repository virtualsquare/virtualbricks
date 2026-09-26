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
The Bricks tab: the list of the bricks, its toolbar, its keys, and the
drop of a brick on another.
"""

from twisted.internet import defer

from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, GObject, Gtk

    from virtualbricks.gui import widgets
    from virtualbricks.gui.mainwindow import bricks
    from virtualbricks.gui.mainwindow.bricks import BricksTab


class FakeGui:
    def __init__(self):
        self.window = object()
        self.configured = []
        self.removed = []
        self.started = []

    def curtain_up(self, brick):
        self.configured.append(brick)

    def ask_remove_brick(self, brick):
        self.removed.append(brick)

    def startstop_brick(self, brick):
        self.started.append(brick)


class FakeDialog:
    def __init__(self, shown, factory):
        self.shown = shown
        self.factory = factory

    def show(self, parent):
        self.shown.append((self.factory, parent))


class FakeSelection:
    def __init__(self, data=b""):
        self.data = data
        self.sent = None

    def get_target(self):
        return "brick-connect-target"

    def set(self, target, format, data):
        self.sent = (target, format, data)

    def get_data(self):
        return self.data


class FakeContext:
    def __init__(self):
        self.finished = []

    def finish(self, success, delete, time):
        self.finished.append((success, delete, time))


class BricksTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(bricks, "logger", self.logger)
        self.gui = FakeGui()
        self.done = []
        self.sw = self.brick("switch", "sw")
        self.tab = BricksTab(self.gui, self.factory)
        self.addCleanup(self.tab.destroy)
        self.view = self.tab.view

    def brick(self, kind, name):
        brick = self.factory.new_brick(kind, name)
        brick.poweron = lambda: defer.succeed(self.done.append(("on", name)))
        brick.poweroff = lambda: self.done.append(("off", name))
        return brick

    def listed(self):
        return [row[0] for row in self.tab.store]

    def select(self, index):
        self.view.get_selection().select_path(Gtk.TreePath(index))


class TestTheList(BricksTestCase):

    def changes(self):
        changed = []
        self.tab.store.connect(
            "row-changed", lambda store, path, itr: changed.append(path)
        )
        return changed

    def test_the_bricks(self):
        changed = self.changes()
        tap = self.brick("tap", "tap")
        self.assertEqual(self.listed(), [self.sw, tap])
        tap.notify_changed()
        self.assertEqual([path.get_indices() for path in changed], [[1]])
        self.factory.del_brick(self.sw)
        self.assertEqual(self.listed(), [tap])

    def test_not_after_quit(self):
        changed = self.changes()
        self.tab.on_quit()
        self.brick("tap", "tap")
        self.sw.notify_changed()
        self.factory.del_brick(self.sw)
        self.assertEqual(self.listed(), [self.sw])
        self.assertEqual(changed, [])

    def test_the_columns(self):
        columns = self.view.get_columns()
        self.assertEqual(
            [column.get_title() for column in columns],
            ["Icon", "Status", "Type", "Name", "Parameters"],
        )
        cells = [column.get_cells()[0] for column in columns]
        self.assertIsInstance(cells[0], widgets.CellRendererBrickIcon)
        self.assertEqual(
            [cell.props.format_string for cell in cells[1:]],
            ["s", "t", "n", "p"],
        )
        model = self.view.get_model()
        columns[3].cell_set_cell_data(
            model, model.get_iter_first(), False, False
        )
        self.assertEqual(cells[3].props.text, "sw")

    def test_the_menu(self):
        releases = []
        self.patch(
            bricks,
            "popup_menu",
            lambda view, event, gui: releases.append((view, gui)) or True,
        )
        event = Gdk.Event.new(Gdk.EventType.BUTTON_RELEASE)
        self.assertTrue(self.view.emit("button-release-event", event))
        self.assertEqual(releases, [(self.view, self.gui)])

    def release_key(self, keyval):
        event = Gdk.Event.new(Gdk.EventType.KEY_RELEASE)
        event.key.keyval = keyval
        self.view.emit("key-release-event", event)

    def test_delete(self):
        self.release_key(Gdk.KEY_Delete)
        # nothing selected
        self.assertEqual(self.gui.removed, [])
        self.select(0)
        self.release_key(Gdk.KEY_Delete)
        self.release_key(Gdk.KEY_BackSpace)
        self.release_key(Gdk.KEY_a)
        self.assertEqual(self.gui.removed, [self.sw, self.sw])

    def test_a_double_click(self):
        self.view.row_activated(Gtk.TreePath(0), self.view.get_column(0))
        self.assertEqual(self.gui.started, [self.sw])

    def test_its_parts_show(self):
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        # else the toolbar keeps its buttons in its overflow menu
        window.set_size_request(900, 400)
        window.add(self.tab)
        window.show()
        tab = self.tab
        for widget in (
            tab.new_button,
            tab.start_button,
            tab.stop_button,
            tab.configure_button,
            tab.view,
        ):
            self.assertTrue(widget.get_mapped(), widget)

    def test_title(self):
        self.assertEqual(self.tab.title, "_Bricks")


class TestTheToolbar(BricksTestCase):

    def test_new(self):
        shown = []
        self.patch(
            bricks,
            "NewBrickDialog",
            lambda factory: FakeDialog(shown, factory),
        )
        self.tab.new_button.emit("clicked")
        self.assertEqual(shown, [(self.factory, self.gui.window)])

    def test_start_and_stop_all(self):
        self.brick("tap", "tap")
        self.tab.start_button.emit("clicked")
        self.tab.stop_button.emit("clicked")
        self.assertEqual(
            self.done,
            [("on", "sw"), ("on", "tap"), ("off", "sw"), ("off", "tap")],
        )

    def test_what_doesnt_start(self):
        tap = self.brick("tap", "tap")
        sw2 = self.brick("switch", "sw2")
        self.sw.poweron = sw2.poweron = lambda: defer.succeed(None)
        tap.poweron = lambda: defer.fail(OSError("no tap"))
        self.successResultOf(self.tab.start_all())
        # only the brick that fails
        self.assertEqual(self.logger.formatted(), ["Brick not started."])

    def test_configure_the_selected(self):
        button = self.tab.configure_button
        self.assertFalse(button.get_sensitive())
        # a tool button gives its tooltip to its button
        self.assertEqual(
            button.get_child().get_tooltip_text(), "No brick selected"
        )
        self.select(0)
        self.assertTrue(button.get_sensitive())
        button.emit("clicked")
        self.assertEqual(self.gui.configured, [self.sw])


class TestDragAndDrop(BricksTestCase):

    def setUp(self):
        super().setUp()
        self.tap = self.brick("tap", "tap")

    def test_the_list_drags_bricks(self):
        target = Gdk.Atom.intern("brick-connect-target", False)
        for targets in (
            self.view.drag_source_get_target_list(),
            self.view.drag_dest_get_target_list(),
        ):
            found, _info = targets.find(target)
            self.assertTrue(found)
        for signal in ("drag-data-get", "drag-data-received"):
            signal_id = GObject.signal_lookup(signal, Gtk.TreeView)
            self.assertTrue(
                GObject.signal_has_handler_pending(
                    self.view, signal_id, 0, True
                ),
                signal,
            )

    def test_the_dragged_brick(self):
        self.select(1)
        selection = FakeSelection()
        self.assertTrue(
            self.tab.on_drag_data_get(self.view, None, selection, 0, 0)
        )
        self.assertEqual(selection.sent, ("brick-connect-target", 8, b"tap"))

    def drop(self, name, row):
        found = None if row is None else (Gtk.TreePath(row), None)
        self.patch(self.view, "get_dest_row_at_pos", lambda x, y: found)
        context = FakeContext()
        self.assertTrue(
            self.tab.on_drag_data_received(
                self.view, context, 1, 2, FakeSelection(name), 0, 42
            )
        )
        self.assertEqual(context.finished, [(True, False, 42)])

    def test_a_plug_on_a_sock(self):
        self.drop(b"tap", 0)
        self.assertIs(self.tap.plugs[0].sock, self.sw.socks[0])

    def test_a_sock_on_a_plug(self):
        self.drop(b"sw", 1)
        self.assertIs(self.tap.plugs[0].sock, self.sw.socks[0])

    def test_nothing_to_connect(self):
        tap2 = self.brick("tap", "tap2")
        self.drop(b"tap", 2)
        self.assertIsNone(self.tap.plugs[0].sock)
        self.assertIsNone(tap2.plugs[0].sock)
        self.assertEqual(
            self.logger.formatted(),
            ["Nothing to connect: neither brick can plug into the other."],
        )

    def test_nothing_happens(self):
        # on itself, an unknown brick, nowhere
        self.drop(b"tap", 1)
        self.drop(b"nobody", 0)
        self.drop(b"tap", None)
        self.assertIsNone(self.tap.plugs[0].sock)
        self.assertEqual(self.logger.formatted(), [])
