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
The Topology tab: when it lays the lab out, its bar and menu, the clicks
on the bricks, and the export.
"""

from twisted.internet import defer

from virtualbricks import topology as layouts
from virtualbricks.bricks import Point, set_places
from virtualbricks.config.settings import (
    ProjectSettings,
    get_setting,
    set_setting,
    use_project,
)
from virtualbricks.config.workspace import projects
from virtualbricks.observable import Observable, Signal
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, GLib, Gtk

    from virtualbricks.gui.mainwindow import picture, topology
    from virtualbricks.gui.mainwindow.bricks import brickmenu
    from virtualbricks.gui.mainwindow.topology import (
        GAP,
        TopologyTab,
        level,
        menu,
        with_extension,
    )
    from virtualbricks.gui.mainwindow.topologyview import LEVELS, fit_zoom


def allocate(widget, width, height):
    # GTK asks the size first
    widget.get_preferred_width()
    widget.get_preferred_height()
    allocation = Gdk.Rectangle()
    allocation.width = width
    allocation.height = height
    widget.size_allocate(allocation)


def run_idle_calls():
    while Gtk.events_pending():
        Gtk.main_iteration()


class FakeMachine:
    """The machine of the bricks, as the tab reads it: the settings."""

    def setting(self, name):
        return get_setting(name)


class FakeEngine:
    """
    The engine of the main window, as the tab reads it: the workspace and
    the settings; and what it connects, places and sets.
    """

    workspace = projects
    local = True
    machine = FakeMachine()

    def __init__(self):
        self.connected = []
        self.placed = []
        self.set = []
        self.refused = None

    def set_settings(self, values):
        self.set.append(values)
        if self.refused is not None:
            return defer.fail(self.refused)
        for name, value in values.items():
            set_setting(name, value)
        return defer.succeed(None)

    def connect(self, brick, other):
        self.connected.append((brick, other))
        if self.refused is not None:
            return defer.fail(self.refused)
        return defer.succeed(True)

    def place(self, places):
        self.placed.append(places)
        if self.refused is not None:
            return defer.fail(self.refused)
        set_places(places)
        return defer.succeed(None)


class FakeMenus:
    def __init__(self):
        self.shown = []

    def popup(self, widget, event, engine, window, brick, configure):
        self.shown.append(
            (widget, brick, event.button, engine, window, configure)
        )
        return self


class FakeDialog:
    def __init__(self, filename, kind=None):
        self.filename = filename
        self.kind = kind
        self.destroyed = False

    def get_filename(self):
        return self.filename

    def get_filter(self):
        return self.kind

    def destroy(self):
        self.destroyed = True


class FakeProject:
    def __init__(self, name):
        self.name = name


class TopologyTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.logger = FakeLogger()
        self.patch(topology, "logger", self.logger)
        self.laid_out = []
        # the lines of each layout
        self.lines = []

        def layout(bricks, direction, measure, lines=layouts.CURVED):
            bricks = list(bricks)
            # the names measured by the view
            self.assertEqual(measure, self.view.measure)
            self.laid_out.append(([b.name for b in bricks], direction))
            self.lines.append(lines)
            return layouts.layout(bricks, direction, measure, lines)

        self.patch(topology, "layout", layout)
        use_project(ProjectSettings())
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.vm = self.factory.new_brick("qemu", "vm")
        self.vm.connect(self.sw1.socks[0])
        self.engine = FakeEngine()
        # what the menus open over: the main window
        self.window = object()
        # what the Bricks tab shows
        self.configured = []
        self.tab = TopologyTab(
            self.engine, self.window, self.factory, self.configured.append
        )
        self.addCleanup(self.tab.destroy)
        self.view = self.tab.view

    def show(self, width=600, height=400):
        self.tab.on_shown()
        allocate(self.tab, width, height)
        run_idle_calls()
        allocate(self.tab, width, height)

    def choose(self, layout):
        """A layout from the menu."""

        self.tab.layout_action.change_state(GLib.Variant.new_string(layout))

    def state(self):
        return self.tab.layout_action.get_state().get_string()

    def in_area(self, brick):
        node = next(n for n in self.view.layout.nodes if n.brick is brick)
        ox, oy = self.view.origin()
        zoom = self.view.zoom
        return ox + node.x * zoom, oy + node.y * zoom


class TestLayingOut(TopologyTestCase):

    def test_when_it_shows(self):
        self.factory.new_brick("switch", "sw0")
        self.assertEqual(self.laid_out, [])
        self.factory.remove_brick(self.factory.get_brick("sw0"))
        self.tab.on_shown()
        self.assertEqual(self.laid_out, [(["sw1", "vm"], "LR")])
        self.assertEqual(
            [node.brick for node in self.view.layout.nodes],
            [self.sw1, self.vm],
        )
        # nothing changed
        self.tab.on_left()
        self.tab.on_shown()
        self.assertEqual(len(self.laid_out), 1)

    def test_after_a_brick_changes(self):
        self.tab.on_shown()
        self.factory.new_brick("switch", "sw2")
        self.assertEqual(self.laid_out[-1], (["sw1", "vm", "sw2"], "LR"))
        # hidden: when it shows again
        self.tab.on_left()
        self.factory.new_brick("switch", "sw3")
        self.assertEqual(len(self.laid_out), 2)
        self.tab.on_shown()
        self.assertEqual(len(self.laid_out), 3)

    def test_not_after_quit(self):
        self.tab.on_shown()
        self.tab.on_quit()
        self.factory.new_brick("switch", "sw2")
        self.assertEqual(len(self.laid_out), 1)

    def test_the_direction(self):
        self.tab.on_shown()
        self.choose("TB")
        self.assertEqual(self.laid_out[-1], (["sw1", "vm"], "TB"))
        self.assertEqual(self.state(), "TB")
        # hidden, it waits
        self.tab.on_left()
        self.choose("LR")
        self.assertEqual(len(self.laid_out), 2)
        self.tab.on_shown()
        self.assertEqual(self.laid_out[-1], (["sw1", "vm"], "LR"))

    def test_by_hand(self):
        self.sw1.place = Point(0, 0)
        self.tab.on_shown()
        # no Graphviz: the places
        self.assertEqual(self.laid_out, [])
        self.assertEqual(
            layouts.places(self.view.layout)[self.sw1], Point(0, 0)
        )
        self.assertEqual(self.state(), "hand")
        self.assertEqual(self.engine.placed, [])

    def test_a_project_by_hand(self):
        self.sw1.place = Point(0, 0)
        tab = TopologyTab(
            self.engine, self.window, self.factory, self.configured.append
        )
        self.addCleanup(tab.destroy)
        self.assertEqual(tab.layout_action.get_state().get_string(), "hand")


class TestByHand(TopologyTestCase):
    """The layout of the menu, by hand or by Graphviz (page 35)."""

    def setUp(self):
        super().setUp()
        self.show()

    def test_by_hand_keeps_the_picture(self):
        self.choose("TB")
        before = {
            node.brick: (node.x, node.y) for node in self.view.layout.nodes
        }
        self.choose("hand")
        # every brick at the place that the picture shows
        [placed] = self.engine.placed
        self.assertEqual(
            placed,
            layouts.places(layouts.layout([self.sw1, self.vm], "TB")),
        )
        self.assertEqual(set(placed), {self.sw1, self.vm})
        self.assertEqual(self.state(), "hand")
        for node in self.view.layout.nodes:
            x, y = before[node.brick]
            # whole points
            self.assertLessEqual(abs(node.x - x), 0.5)
            self.assertLessEqual(abs(node.y - y), 0.5)

    def test_by_hand_again(self):
        self.choose("hand")
        self.choose("hand")
        self.assertEqual(len(self.engine.placed), 1)

    def test_by_hand_without_bricks(self):
        for brick in list(self.factory.bricks):
            self.factory.remove_brick(brick)
        self.choose("hand")
        self.assertEqual(self.engine.placed, [])
        self.assertEqual(self.state(), "LR")

    def test_graphviz_again(self):
        self.choose("hand")
        self.choose("TB")
        # at once, without a question
        self.assertEqual(
            self.engine.placed[-1], {self.sw1: None, self.vm: None}
        )
        self.assertIsNone(self.sw1.place)
        self.assertEqual(self.laid_out[-1], (["sw1", "vm"], "TB"))
        self.assertEqual(self.state(), "TB")

    def test_the_first_move(self):
        shown = layouts.places(self.view.layout)
        self.view.emit("brick-moved", self.sw1, Point(5, 300))
        # every other brick where the picture shows it
        self.assertEqual(
            self.engine.placed,
            [{self.sw1: Point(5, 300), self.vm: shown[self.vm]}],
        )
        self.assertEqual(self.vm.place, shown[self.vm])
        self.assertEqual(self.state(), "hand")
        self.assertEqual(
            layouts.places(self.view.layout)[self.sw1], Point(5, 300)
        )

    def test_a_move_by_hand(self):
        self.choose("hand")
        self.view.emit("brick-moved", self.sw1, Point(5, 300))
        self.assertEqual(self.engine.placed[-1], {self.sw1: Point(5, 300)})
        self.assertEqual(self.sw1.place, Point(5, 300))

    def test_a_move_refused(self):
        self.engine.refused = ValueError("no")
        self.view.emit("brick-moved", self.sw1, Point(5, 300))
        self.assertEqual(self.logger.formatted(), ["Cannot move sw1"])
        self.assertIsNone(self.sw1.place)
        self.assertEqual(self.state(), "LR")

    def test_a_refusal(self):
        self.engine.refused = ValueError("no")
        self.choose("hand")
        self.assertEqual(
            self.logger.formatted(), ["Cannot change the places of the bricks"]
        )
        self.assertEqual(self.state(), "LR")


def at_right_angles(link):
    """Whether each segment of link goes across or down."""

    for i in range(0, len(link.points) - 3, 3):
        xs, ys = zip(*link.points[i : i + 4])
        if max(xs) - min(xs) > 0.1 and max(ys) - min(ys) > 0.1:
            return False
    return True


class TestLinks(TopologyTestCase):
    """The lines of the links, from Links in the menu (page 36)."""

    def setUp(self):
        super().setUp()
        self.routed = []

        def route(lab, lines):
            self.routed.append((lab, lines))
            return layouts.route(lab, lines)

        self.patch(topology, "route", route)
        # sw2 in the way of the link from sw1 to vm
        self.sw2 = self.factory.new_brick("switch", "sw2")
        self.sw1.place, self.sw2.place = Point(0, 0), Point(200, 0)
        self.vm.place = Point(400, 0)
        self.show()

    def choose_lines(self, lines):
        self.tab.lines_action.change_state(GLib.Variant.new_string(lines))

    def lines_state(self):
        return self.tab.lines_action.get_state().get_string()

    def link(self):
        [link] = self.view.layout.links
        return link

    def test_curved_by_default(self):
        self.assertEqual(self.lines_state(), "curved")
        self.assertTrue(self.tab.lines_action.get_enabled())
        # around sw2
        self.assertGreater(len(self.link().points), 4)
        self.assertFalse(at_right_angles(self.link()))
        self.assertEqual([lines for _, lines in self.routed], ["curved"])

    def test_right_angles(self):
        self.choose_lines("right-angles")
        self.assertEqual(self.engine.set, [{"link_lines": "right-angles"}])
        self.assertEqual(get_setting("link_lines"), "right-angles")
        self.assertEqual(self.lines_state(), "right-angles")
        self.assertGreater(len(self.link().points), 4)
        self.assertTrue(at_right_angles(self.link()))

    def test_straight(self):
        self.choose_lines("straight")
        self.assertEqual(get_setting("link_lines"), "straight")
        self.assertEqual(self.lines_state(), "straight")
        self.assertEqual(len(self.link().points), 4)
        # Graphviz doesn't route straight lines
        self.assertEqual(len(self.routed), 1)

    def test_in_every_layout(self):
        self.choose_lines("right-angles")
        self.choose("TB")
        self.assertTrue(self.tab.lines_action.get_enabled())
        self.assertEqual(self.lines[-1], "right-angles")
        for link in self.view.layout.links:
            self.assertTrue(at_right_angles(link), link)
        self.choose_lines("straight")
        self.assertEqual(self.lines[-1], "straight")
        self.assertEqual(self.laid_out[-1][1], "TB")
        self.assertEqual(self.lines_state(), "straight")

    def test_refused(self):
        self.engine.refused = ValueError("no")
        self.choose_lines("right-angles")
        self.assertEqual(self.logger.formatted(), ["Cannot change link_lines"])
        self.assertEqual(self.lines_state(), "curved")
        self.assertFalse(at_right_angles(self.link()))

    def test_changed_elsewhere(self):
        # as the console changes it
        set_setting("link_lines", "right-angles")
        self.assertEqual(self.lines_state(), "right-angles")
        self.assertTrue(at_right_angles(self.link()))
        # another setting changes nothing
        set_setting("qemu_path", "/opt")
        self.assertEqual(len(self.routed), 2)

    def test_hidden(self):
        self.tab.on_left()
        set_setting("link_lines", "right-angles")
        self.assertEqual(self.lines_state(), "right-angles")
        self.assertEqual(len(self.routed), 1)
        self.tab.on_shown()
        self.assertTrue(at_right_angles(self.link()))

    def test_not_after_quit(self):
        self.tab.on_quit()
        set_setting("link_lines", "right-angles")
        self.assertEqual(self.lines_state(), "curved")
        self.assertEqual(len(self.routed), 1)

    def test_routed_again_only_when_the_lab_changes(self):
        self.assertEqual(len(self.routed), 1)
        routes = self.view.layout.links
        # as when a brick starts or stops
        self.factory.brick_changed.notify(self.vm)
        self.assertEqual(len(self.routed), 1)
        self.assertEqual(self.view.layout.links, routes)
        # a move
        set_places({self.vm: Point(400, 200)})
        self.assertEqual(len(self.routed), 2)
        # a link
        self.vm.connect(self.sw2.socks[0])
        self.assertEqual(len(self.routed), 3)
        self.assertEqual(len(self.view.layout.links), 2)
        # the lines
        set_setting("link_lines", "right-angles")
        self.assertEqual(len(self.routed), 4)
        set_setting("link_lines", "curved")
        self.assertEqual(len(self.routed), 5)


class Copy:
    """The copy of the project there: its settings."""

    def __init__(self):
        self.settings = {"link_lines": "curved"}
        self.settings_changed = Signal(Observable(), "settings-changed")

    def take_settings(self, values):
        self.settings = values
        self.settings_changed.notify(self)


class Machine:
    def __init__(self, copy):
        self.copy = copy

    def setting(self, name):
        return self.copy.settings[name]


class EngineThere(FakeEngine):
    """The engine of the windows of --connect: what it sends there."""

    local = False

    def __init__(self):
        super().__init__()
        self.factory = Copy()
        self.machine = Machine(self.factory)

    def set_settings(self, values):
        self.set.append(values)
        return defer.succeed(None)


class TestLinksThere(TopologyTestCase):
    """Links in the windows of --connect (page 36)."""

    def setUp(self):
        super().setUp()
        self.there = EngineThere()
        self.tab = TopologyTab(
            self.there, self.window, self.factory, self.configured.append
        )
        self.addCleanup(self.tab.destroy)
        self.view = self.tab.view
        self.sw1.place = Point(0, 0)
        self.show()

    def lines_state(self):
        return self.tab.lines_action.get_state().get_string()

    def test_sent_there(self):
        self.tab.lines_action.change_state(
            GLib.Variant.new_string("right-angles")
        )
        self.assertEqual(self.there.set, [{"link_lines": "right-angles"}])
        # until it comes back
        self.assertEqual(self.lines_state(), "curved")

    def test_follows_there(self):
        self.there.factory.take_settings({"link_lines": "right-angles"})
        self.assertEqual(self.lines_state(), "right-angles")
        # the settings here are not those there
        set_setting("link_lines", "straight")
        self.assertEqual(self.lines_state(), "right-angles")

    def test_not_after_quit(self):
        self.tab.on_quit()
        self.there.factory.take_settings({"link_lines": "right-angles"})
        self.assertEqual(self.lines_state(), "curved")


class TestTheBar(TopologyTestCase):

    def test_the_level(self):
        self.show()
        self.view.set_zoom(1.25)
        self.assertEqual(self.tab.level_button.get_label(), "125%")
        self.assertFalse(self.tab.fit_button.get_active())
        self.assertEqual(level(0.333), "33%")

    def test_the_buttons(self):
        self.show()
        self.view.set_zoom(1.0)
        self.tab.in_button.clicked()
        self.assertEqual(self.view.zoom, 1.25)
        self.tab.out_button.clicked()
        self.tab.out_button.clicked()
        self.assertEqual(self.view.zoom, 0.8)
        self.tab.level_button.clicked()
        self.assertEqual((self.view.zoom, self.view.fitting), (1.0, False))
        self.tab.fit_button.clicked()
        self.assertTrue(self.view.fitting)
        self.assertTrue(self.tab.fit_button.get_active())

    def test_fit_stays_on(self):
        self.show()
        self.assertTrue(self.tab.fit_button.get_active())
        # a click on the button that is on fits again
        self.tab.fit_button.clicked()
        self.assertTrue(self.view.fitting)
        self.assertTrue(self.tab.fit_button.get_active())

    def test_the_limits(self):
        self.show()
        self.view.set_zoom(LEVELS[-1])
        self.assertFalse(self.tab.in_button.get_sensitive())
        self.assertTrue(self.tab.out_button.get_sensitive())
        self.view.set_zoom(LEVELS[0])
        self.assertFalse(self.tab.out_button.get_sensitive())
        self.assertTrue(self.tab.in_button.get_sensitive())
        # next to the limits
        self.view.set_zoom(LEVELS[1])
        self.assertTrue(self.tab.out_button.get_sensitive())
        self.view.set_zoom(LEVELS[-2])
        self.assertTrue(self.tab.in_button.get_sensitive())

    def test_a_project_without_bricks(self):
        for brick in list(self.factory.bricks):
            self.factory.remove_brick(brick)
        self.show()
        tab = self.tab
        self.assertTrue(tab.hint.get_visible())
        for button in (
            tab.out_button,
            tab.level_button,
            tab.in_button,
            tab.fit_button,
        ):
            self.assertFalse(button.get_sensitive())
        self.assertFalse(tab.fit_button.get_active())
        self.assertFalse(tab.export_action.get_enabled())
        # the menu still sets the layout
        self.assertTrue(tab.menu_button.get_sensitive())
        self.factory.new_brick("switch", "sw")
        self.assertFalse(tab.hint.get_visible())
        self.assertTrue(tab.export_action.get_enabled())
        self.assertTrue(tab.fit_button.get_sensitive())

    def test_the_lab_empties_while_zoomed(self):
        self.show()
        self.view.set_zoom(2.0)
        for brick in list(self.factory.bricks):
            self.factory.remove_brick(brick)
        self.assertTrue(self.tab.hint.get_visible())
        self.assertFalse(self.tab.export_action.get_enabled())
        self.assertFalse(self.tab.in_button.get_sensitive())

    def test_the_buttons_say_what_they_do(self):
        tab = self.tab
        for button, icon, name in (
            (tab.out_button, "zoom-out-symbolic", "Zoom Out"),
            (tab.in_button, "zoom-in-symbolic", "Zoom In"),
            (tab.fit_button, "zoom-fit-best-symbolic", "Fit All"),
            (tab.menu_button, "view-more-symbolic", "More"),
        ):
            self.assertEqual(button.get_image().get_icon_name()[0], icon)
            self.assertEqual(button.get_tooltip_text(), name)
            self.assertEqual(button.get_accessible().get_name(), name)
        # the level button says the level, and what it does after it
        level = tab.level_button.get_accessible()
        self.assertEqual(tab.level_button.get_tooltip_text(), "Zoom to 100%")
        self.assertEqual(level.get_name(), "100%")
        self.assertEqual(level.get_description(), "Zoom to 100%")
        tab.view.set_zoom(1.5)
        self.assertEqual(level.get_name(), "150%")

    def test_in_the_corner(self):
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        # first: a popover in an offscreen window makes GTK complain when
        # the window goes
        self.addCleanup(self.tab.menu_button.get_popover().destroy)
        window.set_size_request(600, 400)
        window.add(self.tab)
        window.show()
        tab = self.tab
        for widget in (
            tab.out_button,
            tab.level_button,
            tab.in_button,
            tab.fit_button,
            tab.menu_button,
            tab.view,
        ):
            self.assertTrue(widget.get_mapped(), widget)
        # an overlay gives each of its children a window: where in the tab
        x, y = tab.bar.translate_coordinates(tab, 0, 0)
        self.assertEqual(y, GAP)
        width = tab.bar.get_allocated_width()
        self.assertEqual(x + width + GAP, tab.get_allocated_width())

    def test_room_for_the_bar(self):
        self.show()
        # measured once the bar has its room
        self.assertEqual(
            self.view.top, self.tab.bar.get_allocated_height() + 2 * GAP
        )
        self.assertGreater(self.view.top, 2 * GAP)
        self.assertAlmostEqual(
            self.view.zoom,
            fit_zoom(self.view.layout, 600, 400 - self.view.top),
        )

    def test_not_measured_after_the_end(self):
        self.tab.on_shown()
        allocate(self.tab, 600, 400)
        self.tab.destroy()
        run_idle_calls()
        self.assertEqual(self.view.top, 0)


class TestTheMenu(TopologyTestCase):

    def items(self, model):
        result = []
        for i in range(model.get_n_items()):
            label = model.get_item_attribute_value(i, "label", None)
            action = model.get_item_attribute_value(i, "action", None)
            target = model.get_item_attribute_value(i, "target", None)
            section = model.get_item_link(i, "section")
            result.append(
                (
                    label and label.get_string(),
                    action and action.get_string(),
                    target and target.get_string(),
                    section and self.items(section),
                )
            )
        return result

    def test_the_menu(self):
        self.assertEqual(
            self.items(menu()),
            [
                (
                    "Layout",
                    None,
                    None,
                    [
                        ("Left to Right", "topology.layout", "LR", None),
                        ("Top to Bottom", "topology.layout", "TB", None),
                        ("By Hand", "topology.layout", "hand", None),
                    ],
                ),
                (
                    "Links",
                    None,
                    None,
                    [
                        ("Straight", "topology.lines", "straight", None),
                        ("Curved", "topology.lines", "curved", None),
                        (
                            "Right Angles",
                            "topology.lines",
                            "right-angles",
                            None,
                        ),
                    ],
                ),
                (
                    None,
                    None,
                    None,
                    [("Export as Image…", "topology.export", None, None)],
                ),
            ],
        )

    def test_the_button_opens_it(self):
        self.assertIsNotNone(self.tab.menu_button.get_menu_model())
        self.assertIsInstance(self.tab.menu_button.get_popover(), Gtk.Popover)

    def test_the_actions_of_the_tab(self):
        group = self.tab.get_action_group("topology")
        self.assertEqual(
            sorted(group.list_actions()), ["export", "layout", "lines"]
        )
        self.assertEqual(group.get_action_state("layout").get_string(), "LR")
        self.assertEqual(
            group.get_action_state("lines").get_string(), "curved"
        )


class TestClicks(TopologyTestCase):

    def setUp(self):
        super().setUp()
        self.menus = FakeMenus()
        self.patch(brickmenu, "popup", self.menus.popup)
        self.show(1000, 800)

    def press(self, brick, button=1, double=False):
        x, y = self.in_area(brick)
        kind = (
            Gdk.EventType._2BUTTON_PRESS
            if double
            else Gdk.EventType.BUTTON_PRESS
        )
        event = Gdk.Event.new(kind)
        event.button.button = button
        event.button.x = x
        event.button.y = y
        return self.view.area.emit("button-press-event", event)

    def test_the_menu_of_a_brick(self):
        self.assertTrue(self.press(self.vm, button=3))
        self.assertEqual(
            self.menus.shown,
            [
                (
                    self.view.area,
                    self.vm,
                    3,
                    self.engine,
                    self.window,
                    self.configured.append,
                )
            ],
        )
        # kept while it shows
        self.assertIs(self.tab._menu, self.menus)

    def test_a_double_click_configures(self):
        self.assertTrue(self.press(self.vm, double=True))
        self.assertEqual(self.configured, [self.vm])
        # one click does nothing
        self.assertTrue(self.press(self.vm))
        self.assertEqual(self.configured, [self.vm])

    def test_not_on_a_brick(self):
        event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
        event.button.button = 3
        event.button.x = event.button.y = 1
        self.assertFalse(self.tab.on_button_press(self.view.area, event))
        self.assertEqual(self.menus.shown, [])


class TestDrops(TopologyTestCase):

    def test_a_drop_connects(self):
        tap = self.factory.new_brick("tap", "tap")
        self.view.emit("brick-dropped", tap, self.sw1)
        self.assertEqual(self.engine.connected, [(tap, self.sw1)])
        self.assertEqual(self.logger.events, [])

    def test_a_failure(self):
        self.engine.refused = RuntimeError("the connection is gone")
        self.view.emit("brick-dropped", self.vm, self.sw1)
        self.assertEqual(self.logger.levels(), ["failure"])
        self.assertEqual(self.logger.formatted(), ["Cannot connect vm to sw1"])


class TestExport(TopologyTestCase):

    def setUp(self):
        super().setUp()
        self.exports = []
        self.error = None

        def export(lab, filename, font):
            if self.error is not None:
                raise self.error
            self.exports.append((lab, filename, font.to_string()))

        self.patch(picture, "export", export)
        self.tab.on_shown()

    def font(self):
        context = self.view.area.get_style_context()
        return context.get_property("font", context.get_state()).to_string()

    def test_export(self):
        self.tab.export("lab.svg")
        self.assertEqual(
            self.exports, [(self.view.layout, "lab.svg", self.font())]
        )
        self.assertEqual(self.logger.formatted(), [])

    def test_failures(self):
        for error, message in (
            (ValueError("jpg"), "Invalid image format"),
            (OSError("full"), "Could not write file"),
            (RuntimeError("?"), "Unknown error"),
        ):
            self.error = error
            self.tab.export("lab.png")
            self.assertEqual(
                self.logger.formatted()[-1],
                f"Error saving topology: {message}",
            )

    def test_the_extension(self):
        self.assertEqual(with_extension("lab.svg", ".pdf"), "lab.svg")
        self.assertEqual(with_extension("lab.PDF", ".png"), "lab.PDF")
        self.assertEqual(with_extension("lab", ".pdf"), "lab.pdf")
        self.assertEqual(with_extension("lab.v2", None), "lab.v2.png")

    def test_the_dialog(self):
        dialog = FakeDialog("lab.png")
        self.tab.on_export_response(dialog, Gtk.ResponseType.OK, {})
        self.assertTrue(dialog.destroyed)
        # the extension of the filter, when the name has none
        kind = object()
        dialog = FakeDialog("lab", kind)
        self.tab.on_export_response(
            dialog, Gtk.ResponseType.OK, {kind: ".pdf"}
        )
        self.assertEqual(
            [filename for _, filename, _ in self.exports],
            ["lab.png", "lab.pdf"],
        )
        dialog = FakeDialog("other.png")
        self.tab.on_export_response(dialog, Gtk.ResponseType.CANCEL, {})
        self.assertTrue(dialog.destroyed)
        self.assertEqual(len(self.exports), 2)

    def chooser(self):
        self.tab.export_action.activate(None)
        [chooser] = [
            window
            for window in Gtk.Window.list_toplevels()
            if isinstance(window, Gtk.FileChooserDialog)
        ]
        self.addCleanup(chooser.destroy)
        return chooser

    def test_the_menu_item(self):
        chooser = self.chooser()
        self.assertTrue(chooser.get_visible())
        self.assertEqual(chooser.get_title(), "Export as Image")
        self.assertEqual(chooser.get_action(), Gtk.FileChooserAction.SAVE)
        self.assertTrue(chooser.get_do_overwrite_confirmation())
        chooser.response(Gtk.ResponseType.CANCEL)
        self.assertNotIn(chooser, Gtk.Window.list_toplevels())

    def test_disabled_without_a_lab(self):
        self.tab.on_left()
        for brick in list(self.factory.bricks):
            self.factory.remove_brick(brick)
        self.tab.on_shown()
        self.tab.export_action.activate(None)
        self.assertFalse(
            any(
                isinstance(window, Gtk.FileChooserDialog)
                for window in Gtk.Window.list_toplevels()
            )
        )

    def test_the_formats(self):
        chooser = self.chooser()
        self.assertEqual(
            [kind.get_name() for kind in chooser.list_filters()],
            ["PNG image", "SVG image", "PDF document"],
        )

    def test_what_each_format_shows(self):
        chooser = self.chooser()

        def shows(kind, name):
            info = Gtk.FileFilterInfo()
            info.contains = Gtk.FileFilterFlags.DISPLAY_NAME
            info.display_name = name
            return kind.filter(info)

        png, svg, pdf = chooser.list_filters()
        for kind, extension in ((png, "png"), (svg, "svg"), (pdf, "pdf")):
            self.assertTrue(shows(kind, f"lab.{extension}"))
            self.assertTrue(shows(kind, f"LAB.{extension.upper()}"))
        self.assertFalse(shows(png, "lab.svg"))
        self.assertFalse(shows(svg, "lab.pdf"))

    def test_the_name(self):
        self.patch(projects, "current", None)
        chooser = self.chooser()
        self.assertEqual(chooser.get_current_name(), "topology.png")
        chooser.destroy()
        self.patch(projects, "current", FakeProject("ospf-lab"))
        chooser = self.chooser()
        self.assertEqual(chooser.get_current_name(), "ospf-lab.png")

    def test_the_name_follows_the_format(self):
        self.patch(projects, "current", None)
        chooser = self.chooser()
        svg, pdf = chooser.list_filters()[1:]
        chooser.set_filter(svg)
        self.assertEqual(chooser.get_current_name(), "topology.svg")
        # not a name of the user's
        chooser.set_current_name("notes.txt")
        chooser.set_filter(pdf)
        self.assertEqual(chooser.get_current_name(), "notes.txt")

    def test_over_its_window(self):
        window = Gtk.Window()
        self.addCleanup(window.destroy)
        self.addCleanup(self.tab.menu_button.get_popover().destroy)
        window.add(self.tab)
        chooser = self.chooser()
        self.assertIs(chooser.get_transient_for(), window)


class TestTheTab(TopologyTestCase):

    def test_title(self):
        self.assertEqual(self.tab.title, "_Topology")

    def test_the_hint(self):
        self.assertEqual(
            self.tab.hint.get_text(),
            "No bricks yet. New Brick, in the Bricks tab, adds one.",
        )
        self.assertTrue(
            self.tab.hint.get_style_context().has_class("dim-label")
        )
        # the clicks go to the picture
        self.assertTrue(self.tab.get_overlay_pass_through(self.tab.hint))
