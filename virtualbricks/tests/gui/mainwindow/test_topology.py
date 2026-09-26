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

"""The Topology tab: when it draws, the clicks on the bricks, the export."""

from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, Gtk

    from virtualbricks.gui import graphics
    from virtualbricks.gui.mainwindow import topology
    from virtualbricks.gui.mainwindow.topology import TopologyTab


class FakeNode:
    def __init__(self, name, x, y):
        self.name = name
        self.x = x
        self.y = y

    def here(self, x, y):
        return (x, y) == (self.x, self.y)


class FakeTopology:
    """The picture that Graphviz would draw: a brick every 10 pixels."""

    error = None

    def __init__(self, drawn, image, bricks, scale, orientation, runtime):
        drawn.append(self)
        self.image = image
        self.orientation = orientation
        self.runtime = runtime
        self.nodes = [
            FakeNode(brick.get_name(), 10 * i, 5)
            for i, brick in enumerate(bricks)
        ]
        self.exported = []

    def export(self, filename):
        if self.error is not None:
            raise self.error
        self.exported.append(filename)


class FakeGui:
    def __init__(self):
        self.started = []

    def startstop_brick(self, brick):
        self.started.append(brick)


class FakeMenu:
    def __init__(self, shown, brick):
        self.shown = shown
        self.brick = brick

    def popup(self, button, time, gui):
        self.shown.append((self.brick, button, gui))


class FakeEvent:
    def __init__(self, x, y, button=1, double=False):
        self.x = x
        self.y = y
        self.button = button
        self.type = (
            Gdk.EventType._2BUTTON_PRESS
            if double
            else Gdk.EventType.BUTTON_PRESS
        )
        self.time = 0

    def get_coords(self):
        return self.x, self.y


class FakeDialog:
    def __init__(self, filename):
        self.filename = filename
        self.destroyed = False

    def get_filename(self):
        return self.filename

    def destroy(self):
        self.destroyed = True


class TopologyTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.drawn = []
        self.patch(
            graphics,
            "Topology",
            lambda *args: FakeTopology(self.drawn, *args),
        )
        self.logger = FakeLogger()
        self.patch(topology, "logger", self.logger)
        self.gui = FakeGui()
        self.tab = TopologyTab(self.gui, self.factory)
        self.addCleanup(self.tab.destroy)

    def orientations(self):
        return [picture.orientation for picture in self.drawn]


class TestDrawing(TopologyTestCase):

    def test_when_it_shows(self):
        self.factory.new_brick("switch", "sw")
        self.assertEqual(self.drawn, [])
        self.tab.on_shown()
        [picture] = self.drawn
        self.assertIs(picture.image, self.tab.image)
        self.assertEqual(picture.runtime, self.factory.runtime_dir)
        # nothing changed
        self.tab.on_left()
        self.tab.on_shown()
        self.assertEqual(len(self.drawn), 1)

    def test_after_a_brick_changes(self):
        self.tab.on_shown()
        self.factory.new_brick("switch", "sw")
        self.assertEqual(len(self.drawn), 2)
        self.assertEqual([n.name for n in self.drawn[-1].nodes], ["sw"])
        # hidden: when it shows again
        self.tab.on_left()
        self.factory.new_brick("switch", "sw2")
        self.assertEqual(len(self.drawn), 2)
        self.tab.on_shown()
        self.assertEqual(len(self.drawn), 3)

    def test_the_orientation(self):
        self.tab.on_shown()
        self.tab.vertical_radio.set_active(True)
        self.tab.horizontal_radio.set_active(True)
        self.assertEqual(self.orientations(), ["LR", "TB", "LR"])

    def test_not_after_quit(self):
        self.tab.on_shown()
        self.tab.on_quit()
        self.factory.new_brick("switch", "sw")
        self.assertEqual(len(self.drawn), 1)

    def test_the_scroll(self):
        adjustment = self.tab.scrolled.get_hadjustment()
        adjustment.configure(0, 0, 100, 1, 10, 10)
        # nothing drawn yet
        adjustment.set_value(20)
        self.tab.on_shown()
        adjustment.set_value(30)
        self.assertEqual(self.drawn[0].x_adj, 30)
        adjustment = self.tab.scrolled.get_vadjustment()
        adjustment.configure(0, 0, 100, 1, 10, 10)
        adjustment.set_value(40)
        self.assertEqual(self.drawn[0].y_adj, 40)


class TestClicks(TopologyTestCase):

    def setUp(self):
        super().setUp()
        self.menus = []
        self.patch(
            topology, "IMenu", lambda brick, _: FakeMenu(self.menus, brick)
        )
        self.factory.new_brick("switch", "sw1")
        self.sw2 = self.factory.new_brick("switch", "sw2")
        self.tab.on_shown()

    def press(self, event):
        return self.tab.on_button_press(self.tab.viewport, event)

    def test_a_double_click_starts_or_stops(self):
        self.assertTrue(self.press(FakeEvent(10, 5, double=True)))
        self.assertEqual(self.gui.started, [self.sw2])
        # one click does nothing
        self.assertTrue(self.press(FakeEvent(10, 5)))
        self.assertEqual(self.gui.started, [self.sw2])

    def test_the_menu(self):
        self.assertTrue(self.press(FakeEvent(10, 5, button=3)))
        self.assertEqual(self.menus, [(self.sw2, 3, self.gui)])

    def test_not_on_a_brick(self):
        self.assertIsNone(self.press(FakeEvent(15, 5, button=3)))
        self.assertIsNone(self.press(FakeEvent(15, 5, double=True)))
        self.assertEqual(self.menus, [])
        self.assertEqual(self.gui.started, [])

    def test_a_real_click(self):
        event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
        event.button.button = 3
        event.button.x = 10
        event.button.y = 5
        self.assertTrue(self.tab.viewport.emit("button-press-event", event))
        self.assertEqual(self.menus, [(self.sw2, 3, self.gui)])

    def test_drawn_first(self):
        tab = TopologyTab(self.gui, self.factory)
        self.addCleanup(tab.destroy)
        self.assertTrue(tab.on_button_press(tab.viewport, FakeEvent(0, 5)))


class TestExport(TopologyTestCase):

    def test_export(self):
        # drawn first
        self.tab.export("lab.png")
        [picture] = self.drawn
        self.assertEqual(picture.exported, ["lab.png"])
        self.assertEqual(self.logger.formatted(), [])

    def test_failures(self):
        self.tab.on_shown()
        for error, message in (
            (KeyError("png"), "Invalid image format"),
            (IOError("full"), "Could not write file"),
            (ValueError("?"), "Unknown error"),
        ):
            FakeTopology.error = error
            self.addCleanup(setattr, FakeTopology, "error", None)
            self.tab.export("lab.png")
            self.assertEqual(
                self.logger.formatted()[-1],
                f"Error saving topology: {message}",
            )

    def test_the_dialog(self):
        dialog = FakeDialog("lab.png")
        self.tab.on_export_response(dialog, Gtk.ResponseType.OK)
        self.assertTrue(dialog.destroyed)
        self.assertEqual(self.drawn[0].exported, ["lab.png"])
        dialog = FakeDialog("other.png")
        self.tab.on_export_response(dialog, Gtk.ResponseType.CANCEL)
        self.assertTrue(dialog.destroyed)
        self.assertEqual(self.drawn[0].exported, ["lab.png"])

    def test_the_button(self):
        self.tab.export_button.clicked()
        [chooser] = [
            window
            for window in Gtk.Window.list_toplevels()
            if isinstance(window, Gtk.FileChooserDialog)
        ]
        self.addCleanup(chooser.destroy)
        self.assertTrue(chooser.get_visible())
        self.assertEqual(chooser.get_action(), Gtk.FileChooserAction.SAVE)
        self.assertTrue(chooser.get_do_overwrite_confirmation())
        chooser.response(Gtk.ResponseType.CANCEL)
        self.assertNotIn(chooser, Gtk.Window.list_toplevels())


class TestTheTab(TopologyTestCase):

    def test_title(self):
        self.assertEqual(self.tab.title, "_Topology")

    def test_its_parts_show(self):
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        window.add(self.tab)
        window.show()
        tab = self.tab
        for widget in (
            tab.export_button,
            tab.export_button.get_child().get_children()[0],
            tab.export_button.get_child().get_children()[1],
            tab.horizontal_radio,
            tab.vertical_radio,
            tab.image,
        ):
            self.assertTrue(widget.get_mapped(), widget)
        self.assertEqual(
            [
                c.get_label()
                for c in tab.export_button.get_child().get_children()[1:]
            ],
            ["Export as Image"],
        )
        self.assertTrue(tab.horizontal_radio.get_active())
