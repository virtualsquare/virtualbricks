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

"""The Events tab: the list of the events, its toolbar and its keys."""

from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui import widgets
    from virtualbricks.gui.mainwindow import events
    from virtualbricks.gui.mainwindow.events import EventsTab


class FakeGui:
    def __init__(self):
        self.window = object()
        self.configured = []
        self.removed = []

    def curtain_up(self, event):
        self.configured.append(event)

    def ask_remove_event(self, event):
        self.removed.append(event)


class FakeDialog:
    def __init__(self, shown, gui):
        self.shown = shown
        self.gui = gui

    def show(self, parent):
        self.shown.append((self.gui, parent))


class TestEventsTab(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.gui = FakeGui()
        self.done = []
        self.ev1 = self.event("ev1")
        self.tab = EventsTab(self.gui, self.factory)
        self.addCleanup(self.tab.destroy)
        self.view = self.tab.view

    def event(self, name):
        event = self.factory.new_event(name)
        event.poweron = lambda: self.done.append(("on", name))
        event.poweroff = lambda: self.done.append(("off", name))
        event.toggle = lambda: self.done.append(("toggle", name))
        return event

    def listed(self):
        return [row[0] for row in self.tab.store]

    def select(self, index):
        self.view.get_selection().select_path(Gtk.TreePath(index))

    def changes(self):
        changed = []
        self.tab.store.connect(
            "row-changed", lambda store, path, itr: changed.append(path)
        )
        return changed

    def test_the_events(self):
        changed = self.changes()
        ev2 = self.event("ev2")
        self.assertEqual(self.listed(), [self.ev1, ev2])
        ev2.changed.notify(ev2)
        self.assertEqual([path.get_indices() for path in changed], [[1]])
        self.factory.del_event(self.ev1)
        self.assertEqual(self.listed(), [ev2])

    def test_not_after_quit(self):
        changed = self.changes()
        self.tab.on_quit()
        self.event("ev2")
        self.ev1.changed.notify(self.ev1)
        self.factory.del_event(self.ev1)
        self.assertEqual(self.listed(), [self.ev1])
        self.assertEqual(changed, [])

    def test_the_columns(self):
        columns = self.view.get_columns()
        self.assertEqual(
            [column.get_title() for column in columns],
            ["Icon", "Status", "Name", "Parameters"],
        )
        cells = [column.get_cells()[0] for column in columns]
        self.assertIsInstance(cells[0], widgets.CellRendererBrickIcon)
        self.assertEqual(
            [cell.props.format_string for cell in cells[1:]],
            ["s", "n", "p"],
        )
        name = columns[2]
        model = self.view.get_model()
        name.cell_set_cell_data(model, model.get_iter_first(), False, False)
        self.assertEqual(cells[2].props.text, "ev1")

    def test_new(self):
        shown = []
        self.patch(
            events, "NewEventDialog", lambda gui: FakeDialog(shown, gui)
        )
        self.tab.new_button.emit("clicked")
        self.assertEqual(shown, [(self.gui, self.gui.window)])

    def test_start_and_stop_all(self):
        self.event("ev2")
        self.tab.start_button.emit("clicked")
        self.tab.stop_button.emit("clicked")
        self.assertEqual(
            self.done,
            [("on", "ev1"), ("on", "ev2"), ("off", "ev1"), ("off", "ev2")],
        )

    def test_configure_the_selected(self):
        button = self.tab.configure_button
        self.assertFalse(button.get_sensitive())
        # a tool button gives its tooltip to its button
        self.assertEqual(
            button.get_child().get_tooltip_text(), "No event selected"
        )
        self.select(0)
        self.assertTrue(button.get_sensitive())
        button.emit("clicked")
        self.assertEqual(self.gui.configured, [self.ev1])

    def test_the_menu(self):
        releases = []
        self.patch(
            events,
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
        self.assertEqual(self.gui.removed, [self.ev1, self.ev1])

    def test_a_double_click(self):
        self.view.row_activated(Gtk.TreePath(0), self.view.get_column(0))
        self.assertEqual(self.done, [("toggle", "ev1")])

    def test_title(self):
        self.assertEqual(self.tab.title, "_Events")

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
        self.assertEqual(
            [b.get_label() for b in (tab.new_button, tab.configure_button)],
            ["New Event", "Configure"],
        )
