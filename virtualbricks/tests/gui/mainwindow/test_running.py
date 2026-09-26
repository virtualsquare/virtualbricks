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

"""The Running tab: the bricks that run, checked again, and their menu."""

from twisted.internet import task

from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui import widgets
    from virtualbricks.gui.mainwindow import running
    from virtualbricks.gui.mainwindow.running import REFRESH, RunningTab


class FakeMenu:
    def __init__(self, shown, brick):
        self.shown = shown
        self.brick = brick

    def popup(self, button, time, gui):
        self.shown.append((self.brick, button, gui))


class TestRunningTab(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.running = set()
        self.store = widgets.List()
        self.bricks = []
        for name in ("sw1", "sw2", "sw3"):
            brick = self.factory.new_brick("switch", name)
            brick.__isrunning__ = lambda name=name: name in self.running
            self.store.append((brick,))
            self.bricks.append(brick)
        self.clock = task.Clock()
        self.gui = object()
        self.tab = RunningTab(self.gui, self.store, self.clock)
        self.addCleanup(self.tab.destroy)

    def listed(self):
        return [row[0].get_name() for row in self.tab.view.get_model()]

    def test_what_runs(self):
        self.assertEqual(self.listed(), [])
        self.running.update(("sw1", "sw3"))
        # checked again after a while
        self.assertEqual(self.listed(), [])
        self.clock.advance(REFRESH)
        self.assertEqual(self.listed(), ["sw1", "sw3"])
        self.running.discard("sw1")
        self.clock.advance(REFRESH)
        self.assertEqual(self.listed(), ["sw3"])

    def test_no_check_after_the_end(self):
        self.tab.destroy()
        self.assertEqual(self.clock.getDelayedCalls(), [])

    def test_the_columns(self):
        columns = self.tab.view.get_columns()
        self.assertEqual(
            [column.get_title() for column in columns],
            ["Icon", "Pid", "Type", "Name"],
        )
        cells = [column.get_cells()[0] for column in columns]
        self.assertIsInstance(cells[0], widgets.CellRendererBrickIcon)
        self.assertEqual(
            [cell.props.format_string for cell in cells[1:]],
            ["d", "t", "n"],
        )
        self.assertTrue(
            all(cell.props.formatting_enabled for cell in cells[1:])
        )

    def test_a_row(self):
        self.running.add("sw2")
        self.clock.advance(REFRESH)
        model = self.tab.view.get_model()
        name = self.tab.view.get_columns()[3]
        name.cell_set_cell_data(model, model.get_iter_first(), False, False)
        self.assertEqual(name.get_cells()[0].props.text, "sw2")

    def test_the_menu(self):
        menus = []
        self.patch(running, "IJobMenu", lambda brick: FakeMenu(menus, brick))
        self.running.update(("sw1", "sw2"))
        self.clock.advance(REFRESH)
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        # the focus is somewhere else first
        box = Gtk.Box(visible=True)
        box.pack_start(Gtk.Entry(visible=True), False, False, 0)
        box.pack_start(self.tab, True, True, 0)
        window.add(box)
        window.show()
        self.assertIsNot(window.get_focus(), self.tab.view)
        view = self.tab.view
        row = view.get_background_area(Gtk.TreePath(1), None)

        def release(button, y):
            event = Gdk.Event.new(Gdk.EventType.BUTTON_RELEASE)
            event.button.button = button
            event.button.x = row.x + 1
            event.button.y = y
            return view.emit("button-release-event", event)

        self.assertTrue(release(3, row.y + 1))
        self.assertEqual(menus, [(self.bricks[1], 3, self.gui)])
        path, _column = view.get_cursor()
        self.assertEqual(path.get_indices(), [1])
        self.assertIs(window.get_focus(), view)
        # not the right button, or not on a brick
        self.assertFalse(release(1, row.y + 1))
        self.assertFalse(release(3, row.y + 10 * row.height))
        self.assertEqual(len(menus), 1)

    def test_title(self):
        self.assertEqual(self.tab.title, "R_unning")
