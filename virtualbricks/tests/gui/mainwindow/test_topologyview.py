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

"""The picture of a lab: the zoom, where things are, drawing, the input."""

import cairo
from twisted.trial import unittest

from virtualbricks.tests.gui import GuiTestCase, has_display
from virtualbricks.topology import ICON, Layout, layout

if has_display:
    from gi.repository import Gdk, Gtk, Pango

    from virtualbricks.gui.mainwindow import topologyview
    from virtualbricks.gui.mainwindow.topologyview import (
        LEVELS,
        MARGIN,
        TopologyView,
        fit_zoom,
        origin,
        scaled_font,
        tooltip_text,
        zoom_in,
        zoom_out,
    )


def allocate(widget, width, height):
    # GTK asks the size first
    widget.get_preferred_width()
    widget.get_preferred_height()
    allocation = Gdk.Rectangle()
    allocation.width = width
    allocation.height = height
    widget.size_allocate(allocation)


class FakeEvent:
    def __init__(self, x=0, y=0, **attrs):
        self.x = x
        self.y = y
        self.x_root = x
        self.y_root = y
        self.button = 1
        self.state = 0
        self.direction = None
        self.delta_y = 0.0
        self.keyval = 0
        self.__dict__.update(attrs)


class TestZoomLevels(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"

    def test_in_and_out(self):
        self.assertEqual(zoom_in(1.0), 1.25)
        self.assertEqual(zoom_out(1.0), 0.8)
        # between two levels
        self.assertEqual(zoom_in(0.75), 0.8)
        self.assertEqual(zoom_out(0.75), 0.67)
        # the limits
        self.assertEqual(zoom_in(4.0), 4.0)
        self.assertEqual(zoom_out(0.1), 0.1)
        self.assertEqual(zoom_out(0.05), 0.1)
        # a level a little off is that level
        self.assertEqual(zoom_in(0.9999), 1.25)
        self.assertEqual(zoom_out(1.0001), 0.8)

    def test_every_level(self):
        zoom, seen = LEVELS[0], [LEVELS[0]]
        while zoom != LEVELS[-1]:
            zoom = zoom_in(zoom)
            seen.append(zoom)
        self.assertEqual(tuple(seen), LEVELS)

    def test_fit(self):
        lab = Layout(608, 253, (object(),), ())
        # never above 100%
        self.assertEqual(fit_zoom(lab, 1000, 1000), 1.0)
        self.assertAlmostEqual(fit_zoom(lab, 400, 1000), 360 / 608)
        self.assertAlmostEqual(fit_zoom(lab, 1000, 200), 160 / 253)
        # the floor
        self.assertEqual(fit_zoom(lab, 60, 60), 0.1)
        self.assertEqual(fit_zoom(Layout(), 10, 10), 1.0)

    def test_origin(self):
        # in the middle when it fits, else after the margin
        self.assertEqual(origin(100, 2.0, 400), 100)
        self.assertEqual(origin(100, 2.0, 220), MARGIN)
        self.assertEqual(origin(100, 1.0, 50), MARGIN)

    def test_the_font_of_the_names(self):
        font = Pango.FontDescription.from_string("Sans 10")
        self.assertEqual(scaled_font(font, 2.0).get_size(), 20 * Pango.SCALE)
        self.assertEqual(font.get_size(), 10 * Pango.SCALE)
        font.set_absolute_size(12 * Pango.SCALE)
        big = scaled_font(font, 0.5)
        self.assertTrue(big.get_size_is_absolute())
        self.assertEqual(big.get_size(), 6 * Pango.SCALE)
        # never nothing
        self.assertEqual(scaled_font(font, 0.0).get_size(), 1)


class ViewTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.sw2 = self.factory.new_brick("switch", "sw2")
        self.vm = self.factory.new_brick("qemu", "vm")
        self.vm.connect(self.sw1.socks[0])
        self.vm.connect(self.sw2.socks[0])
        self.running = {"sw1"}
        for brick in self.factory.bricks:
            brick.__isrunning__ = lambda name=brick.name: name in self.running
        self.lab = layout(self.factory.bricks)
        self.view = TopologyView()
        self.addCleanup(self.view.destroy)
        self.changes = []
        self.view.connect(
            "zoom-changed",
            lambda view: self.changes.append((view.zoom, view.fitting)),
        )

    def show(self, width=400, height=300, lab=None):
        allocate(self.view, width, height)
        self.view.set_layout(self.lab if lab is None else lab)
        # allocated again, at the size of the zoom
        allocate(self.view, width, height)

    def node(self, name):
        return next(n for n in self.view.layout.nodes if n.brick.name == name)

    def in_area(self, node):
        """The centre of a node's icon, in the area."""

        ox, oy = self.view.origin()
        zoom = self.view.zoom
        top = node.y - node.height / 2
        return ox + node.x * zoom, oy + (top + ICON / 2) * zoom

    def scroll(self):
        return (
            self.view.get_hadjustment().get_value(),
            self.view.get_vadjustment().get_value(),
        )


class TestTheZoom(ViewTestCase):

    def test_fitted_first(self):
        self.show(400, 300)
        self.assertTrue(self.view.fitting)
        self.assertAlmostEqual(self.view.zoom, fit_zoom(self.lab, 400, 300))
        self.assertEqual(self.changes[-1], (self.view.zoom, True))

    def test_the_area_has_the_size_of_the_zoom(self):
        self.show(200, 200)
        self.view.set_zoom(2.0)
        width, height = self.view.area.get_size_request()
        self.assertEqual(width, round(self.lab.width * 2 + 2 * MARGIN))
        self.assertEqual(height, round(self.lab.height * 2 + 2 * MARGIN))
        self.view.set_layout(Layout())
        self.assertEqual(tuple(self.view.area.get_size_request()), (-1, -1))

    def test_zoom_in_and_out(self):
        self.show()
        self.view.zoom_to_100()
        self.view.zoom_in()
        self.assertEqual(self.changes[-1], (1.25, False))
        self.view.zoom_out()
        self.view.zoom_out()
        self.assertEqual(self.changes[-1], (0.8, False))
        self.view.set_zoom(9)
        self.assertEqual(self.view.zoom, LEVELS[-1])

    def test_fit_again(self):
        self.show(400, 300)
        self.view.set_zoom(2.0)
        self.view.fit()
        self.assertEqual(
            self.changes[-1], (fit_zoom(self.lab, 400, 300), True)
        )

    def test_fitted_again_after_a_new_size(self):
        self.show(400, 300)
        allocate(self.view, 300, 200)
        # not while GTK gives out the room
        self.assertAlmostEqual(self.view.zoom, fit_zoom(self.lab, 400, 300))
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertAlmostEqual(self.view.zoom, fit_zoom(self.lab, 300, 200))

    def test_not_fitted_again_after_a_zoom(self):
        self.show(400, 300)
        self.view.set_zoom(2.0)
        allocate(self.view, 300, 200)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertEqual(self.view.zoom, 2.0)

    def test_no_fit_after_the_end(self):
        self.show(400, 300)
        allocate(self.view, 300, 200)
        fits = []
        self.patch(self.view, "fit", lambda: fits.append(1))
        self.view.destroy()
        while Gtk.events_pending():
            Gtk.main_iteration()
        # a destroyed view has no adjustments to fit with
        self.assertEqual(fits, [])

    def test_a_new_layout_fits_when_fitting(self):
        self.show(400, 300)
        bigger = layout(self.factory.bricks, "TB")
        self.view.set_layout(bigger)
        self.assertAlmostEqual(self.view.zoom, fit_zoom(bigger, 400, 300))
        self.view.set_zoom(2.0)
        self.view.set_layout(self.lab)
        self.assertEqual(self.view.zoom, 2.0)

    def test_around_a_point(self):
        # scrolled at 100% too, room to keep vm where it is at 200%
        self.show(200, 100)
        self.view.zoom_to_100()
        allocate(self.view, 200, 100)
        vm = self.node("vm")
        x, y = self.in_area(vm)
        h, v = self.scroll()
        anchor = (x - h, y - v)
        self.view.set_zoom(2.0, anchor)
        # the scroll waits for the area's new size
        allocate(self.view, 200, 100)
        x, y = self.in_area(vm)
        h, v = self.scroll()
        self.assertAlmostEqual(x - h, anchor[0], delta=1)
        self.assertAlmostEqual(y - v, anchor[1], delta=1)

    def test_around_the_centre(self):
        self.show(300, 200)
        self.view.zoom_to_100()
        allocate(self.view, 300, 200)
        h, v = self.scroll()
        centre = self.view.to_layout(h + 150, v + 100)
        self.view.zoom_in()
        allocate(self.view, 300, 200)
        h, v = self.scroll()
        x, y = self.view.to_layout(h + 150, v + 100)
        self.assertAlmostEqual(x, centre[0], delta=1)
        self.assertAlmostEqual(y, centre[1], delta=1)


class TestWhereThingsAre(ViewTestCase):

    def test_the_bricks(self):
        self.show(1000, 1000)
        for node in self.view.layout.nodes:
            x, y = self.in_area(node)
            self.assertIs(self.view.brick_at(x, y), node.brick)
            self.assertIs(self.view.node_at(x, y), node)
        # the name is the brick's too
        vm = self.node("vm")
        x, y = self.in_area(vm)
        self.assertIs(self.view.brick_at(x, y + ICON / 2 + 5), self.vm)
        self.assertIsNone(self.view.brick_at(1, 1))

    def test_the_edges_of_a_box(self):
        self.show(1000, 1000)
        node = self.node("vm")
        ox, oy = self.view.origin()
        left, right = (
            ox + node.x - node.width / 2,
            ox + node.x + node.width / 2,
        )
        top, bottom = (
            oy + node.y - node.height / 2,
            oy + node.y + node.height / 2,
        )
        x, y = ox + node.x, oy + node.y
        for inside in (
            (left + 1, y),
            (right - 1, y),
            (x, top + 1),
            (x, bottom - 1),
        ):
            self.assertIs(self.view.brick_at(*inside), self.vm, inside)
        for outside in (
            (left - 1, y),
            (right + 1, y),
            (x, top - 1),
            (x, bottom + 1),
        ):
            self.assertIsNot(self.view.brick_at(*outside), self.vm, outside)

    def test_at_another_zoom(self):
        self.show(1000, 1000)
        self.view.set_zoom(0.5)
        allocate(self.view, 1000, 1000)
        x, y = self.in_area(self.node("sw2"))
        self.assertIs(self.view.brick_at(x, y), self.sw2)

    def test_in_the_middle(self):
        self.show(1000, 1000)
        ox, oy = self.view.origin()
        self.assertEqual(ox, (1000 - self.lab.width) / 2)
        self.assertEqual(oy, (1000 - self.lab.height) / 2)
        self.assertEqual(self.view.to_layout(ox + 10, oy + 20), (10, 20))


class TestDrawing(ViewTestCase):

    def draw(self, width=None, height=None):
        area = self.view.area
        width = width or area.get_allocated_width()
        height = height or area.get_allocated_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        self.view.on_draw(area, cairo.Context(surface))
        surface.flush()
        return surface

    def pixel(self, surface, x, y):
        data = surface.get_data()
        offset = int(y) * surface.get_stride() + int(x) * 4
        b, g, r, a = data[offset : offset + 4]
        return r, g, b

    def colours(self, surface, node):
        """The colours of a node's icon."""

        x, y = self.in_area(node)
        half = int(ICON * self.view.zoom / 2) - 2
        return {
            self.pixel(surface, x + dx, y + dy)
            for dx in range(-half, half, 2)
            for dy in range(-half, half, 2)
        }

    def luminance(self, colours):
        return min(r + g + b for r, g, b in colours)

    def zoomed(self, zoom):
        self.show(1000, 1000)
        self.view.set_zoom(zoom)
        allocate(self.view, 1000, 1000)

    def test_running_in_colour_stopped_in_grey(self):
        self.zoomed(2.0)
        surface = self.draw()
        coloured = self.colours(surface, self.node("sw1"))
        self.assertTrue(any(len({r, g, b}) > 1 for r, g, b in coloured))
        grey = self.colours(surface, self.node("sw2"))
        self.assertGreater(len(grey), 10)
        self.assertTrue(
            all(abs(r - g) <= 2 and abs(g - b) <= 2 for r, g, b in grey)
        )

    def test_a_stopped_brick_is_faded(self):
        self.show(1000, 1000)
        surface = self.draw()
        running = self.colours(surface, self.node("sw1"))
        stopped = self.colours(surface, self.node("sw2"))
        self.assertGreater(
            self.luminance(stopped), self.luminance(running) + 60
        )

    def test_the_icons_at_their_size(self):
        self.zoomed(2.0)
        surface = self.draw()
        background = self.pixel(surface, 2, 2)
        x, y = self.in_area(self.node("sw1"))
        # beside the icon, above the links
        side = ICON * self.view.zoom / 2
        beside = {
            self.pixel(surface, x + side + dx, y - side / 2)
            for dx in range(2, int(side))
        }
        self.assertEqual(beside, {background})

    def name_colours(self, surface, node):
        """The colours of the line of a node's name."""

        x, y = self.in_area(node)
        zoom = self.view.zoom
        top = y + ICON * zoom / 2 + 2
        return {
            self.pixel(surface, x + dx, top + dy)
            for dx in range(-20, 20)
            for dy in range(0, int(16 * zoom))
        }

    def test_the_names(self):
        self.zoomed(2.0)
        surface = self.draw()
        background = self.pixel(surface, 2, 2)
        running = self.name_colours(surface, self.node("sw1"))
        stopped = self.name_colours(surface, self.node("sw2"))
        self.assertGreater(len(running - {background}), 20)
        # a stopped brick's name is fainter
        self.assertGreater(
            self.luminance(stopped), self.luminance(running) + 60
        )

    def name_height(self, zoom):
        """How many rows of pixels the name of sw1 takes."""

        self.zoomed(zoom)
        surface = self.draw()
        background = self.pixel(surface, 2, 2)
        x, y = self.in_area(self.node("sw1"))
        top = int(y + ICON * zoom / 2)
        rows = [
            dy
            for dy in range(0, int(40 * zoom))
            if any(
                self.pixel(surface, x + dx, top + dy) != background
                for dx in range(-20, 20)
            )
        ]
        return max(rows) - min(rows) + 1

    def test_the_names_follow_the_zoom(self):
        self.assertGreater(self.name_height(2.0), 1.6 * self.name_height(1.0))

    def test_the_brick_under_the_pointer(self):
        self.show(1000, 1000)
        vm = self.node("vm")
        x, y = self.in_area(vm)
        # beside the icon, in the disc
        spot = (x + ICON / 2 + 3, y)
        before = self.pixel(self.draw(), *spot)
        self.view.hover = vm
        after = self.pixel(self.draw(), *spot)
        self.assertNotEqual(before, after)
        # the selection colour, a blue in Adwaita
        r, g, b = after
        self.assertGreater(b, r + 10)

    def test_the_theme(self):
        self.show(1000, 1000)
        light = self.pixel(self.draw(), 2, 2)
        style = Gtk.CssProvider()
        style.load_from_data(b".view { background-color: #102030; }")
        self.view.area.get_style_context().add_provider(
            style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        dark = self.pixel(self.draw(), 2, 2)
        self.assertNotEqual(light, dark)
        self.assertEqual(dark, (0x10, 0x20, 0x30))

    def test_the_links(self):
        self.show(1000, 1000)
        surface = self.draw()
        ox, oy = self.view.origin()
        # the middle of a link, in the text colour made fainter
        link = self.view.layout.links[0]
        x, y = link.points[len(link.points) // 2]
        ink = self.view.area.get_style_context().get_color(
            Gtk.StateFlags.NORMAL
        )
        background = self.pixel(surface, 2, 2)
        darkest = min(
            (self.pixel(surface, ox + x, oy + y + dy) for dy in (-1, 0, 1)),
            key=sum,
        )
        expected = [
            round(
                255 * c * topologyview.LINK_ALPHA
                + b * (1 - topologyview.LINK_ALPHA)
            )
            for c, b in zip((ink.red, ink.green, ink.blue), background)
        ]
        # drawn, and no darker than the text colour made fainter: across
        # two rows of pixels, it can be lighter
        self.assertLess(sum(darkest), sum(background))
        for got, want in zip(darkest, expected):
            self.assertGreaterEqual(got, want - 10)

    def test_nothing_to_draw(self):
        self.show(200, 200, lab=Layout())
        surface = self.draw(200, 200)
        self.assertEqual(
            {self.pixel(surface, x, 100) for x in range(0, 200, 10)},
            {self.pixel(surface, 2, 2)},
        )

    def test_the_icons_once(self):
        icon = self.view._icon(self.sw1, True)
        self.assertIs(self.view._icon(self.sw2, True), icon)
        self.assertIsNot(self.view._icon(self.sw1, False), icon)
        # a virtual machine's own icon, not there
        self.vm.config.icon = "/nowhere.png"
        self.assertIsNone(self.view._icon(self.vm, True))


class TestInput(ViewTestCase):

    def test_ctrl_and_the_wheel(self):
        self.show(300, 200)
        self.view.zoom_to_100()
        control = Gdk.ModifierType.CONTROL_MASK
        up = FakeEvent(50, 50, state=control, direction=Gdk.ScrollDirection.UP)
        self.assertTrue(self.view.on_scroll(self.view.area, up))
        self.assertEqual(self.view.zoom, 1.25)
        down = FakeEvent(
            50, 50, state=control, direction=Gdk.ScrollDirection.DOWN
        )
        self.view.on_scroll(self.view.area, down)
        self.assertEqual(self.view.zoom, 1.0)
        # without Ctrl the view scrolls
        plain = FakeEvent(50, 50, direction=Gdk.ScrollDirection.UP)
        self.assertFalse(self.view.on_scroll(self.view.area, plain))
        self.assertEqual(self.view.zoom, 1.0)

    def test_a_touchpad(self):
        self.show(300, 200)
        self.view.zoom_to_100()
        smooth = Gdk.ScrollDirection.SMOOTH
        control = Gdk.ModifierType.CONTROL_MASK
        for _ in range(3):
            self.view.on_scroll(
                self.view.area,
                FakeEvent(state=control, direction=smooth, delta_y=-0.4),
            )
        # a step for each whole unit
        self.assertEqual(self.view.zoom, 1.25)
        self.view.on_scroll(
            self.view.area,
            FakeEvent(state=control, direction=smooth, delta_y=2.2),
        )
        self.assertEqual(self.view.zoom, 0.8)

    def key(self, keyval, state=0):
        event = FakeEvent(keyval=keyval, state=state)
        return self.view.on_key_press(self.view.area, event)

    def test_the_keys(self):
        self.show(300, 200)
        self.view.zoom_to_100()
        control = Gdk.ModifierType.CONTROL_MASK
        shift = Gdk.ModifierType.SHIFT_MASK
        self.assertTrue(self.key(Gdk.KEY_plus, control | shift))
        self.assertEqual(self.view.zoom, 1.25)
        self.key(Gdk.KEY_equal, control)
        self.key(Gdk.KEY_KP_Add, control)
        self.assertEqual(self.view.zoom, 2.0)
        self.key(Gdk.KEY_minus, control)
        self.key(Gdk.KEY_KP_Subtract, control)
        self.assertEqual(self.view.zoom, 1.25)
        self.key(Gdk.KEY_0, control)
        self.assertEqual((self.view.zoom, self.view.fitting), (1.0, False))
        self.assertTrue(self.key(Gdk.KEY_f))
        self.assertTrue(self.view.fitting)
        # not these
        self.assertFalse(self.key(Gdk.KEY_a, control))
        self.assertFalse(self.key(Gdk.KEY_f, Gdk.ModifierType.MOD1_MASK))
        self.assertFalse(self.key(Gdk.KEY_a))

    def test_the_arrows(self):
        self.show(200, 150)
        self.view.set_zoom(3.0)
        allocate(self.view, 200, 150)
        self.view.get_hadjustment().set_value(0)
        self.view.get_vadjustment().set_value(0)
        h, v = self.scroll()
        self.key(Gdk.KEY_Right)
        self.key(Gdk.KEY_Down)
        self.assertEqual(self.scroll(), (h + 40, v + 40))
        self.key(Gdk.KEY_Left)
        self.key(Gdk.KEY_Up)
        self.assertEqual(self.scroll(), (h, v))
        page = self.view.get_vadjustment().get_page_increment()
        self.assertTrue(self.key(Gdk.KEY_Page_Down))
        self.assertEqual(self.scroll(), (h, v + page))
        self.key(Gdk.KEY_Page_Up)
        self.assertEqual(self.scroll(), (h, v))

    def test_drag_the_background(self):
        self.show(200, 150)
        self.view.set_zoom(3.0)
        allocate(self.view, 200, 150)
        self.view.get_hadjustment().set_value(100)
        self.view.get_vadjustment().set_value(100)
        area = self.view.area
        self.assertTrue(self.view.on_button_press(area, FakeEvent(1, 1)))
        self.view.on_motion(area, FakeEvent(-29, -9))
        self.assertEqual(self.scroll(), (130, 110))
        self.assertTrue(self.view.on_button_release(area, FakeEvent(-29, -9)))
        # no more
        self.view.on_motion(area, FakeEvent(-100, -100))
        self.assertEqual(self.scroll(), (130, 110))
        self.assertFalse(self.view.on_button_release(area, FakeEvent()))

    def test_the_cursors(self):
        self.show(1000, 1000)
        cursors = []
        self.patch(self.view, "_set_cursor", cursors.append)
        area = self.view.area
        x, y = self.in_area(self.node("vm"))
        self.view.on_motion(area, FakeEvent(x, y))
        self.view.on_motion(area, FakeEvent(1, 1))
        self.view.on_button_press(area, FakeEvent(1, 1))
        self.view.on_button_release(area, FakeEvent(1, 1))
        self.assertEqual(cursors, ["pointer", None, "grabbing", None])

    def test_the_cursor_of_the_window(self):
        window = Gtk.OffscreenWindow()
        self.addCleanup(window.destroy)
        window.add(self.view)
        window.show()
        # a cursor of GTK 3 doesn't tell its name
        self.patch(Gdk.Cursor, "new_from_name", lambda display, name: name)
        cursors = []
        self.patch(self.view.area.get_window(), "set_cursor", cursors.append)
        self.view._set_cursor("pointer")
        self.view._set_cursor(None)
        self.assertEqual(cursors, ["pointer", None])

    def test_no_cursor_before_a_window(self):
        self.assertIsNone(self.view._set_cursor("pointer"))

    def test_redrawn_when_the_brick_changes(self):
        self.show(1000, 1000)
        area = self.view.area
        drawn, queried = [], []
        self.patch(area, "queue_draw", lambda: drawn.append(1))
        self.patch(area, "trigger_tooltip_query", lambda: queried.append(1))
        x, y = self.in_area(self.node("vm"))
        self.view.on_motion(area, FakeEvent(x, y))
        self.view.on_motion(area, FakeEvent(x + 1, y))
        self.assertEqual((len(drawn), len(queried)), (1, 1))
        self.view.on_leave(area, FakeEvent())
        self.view.on_leave(area, FakeEvent())
        self.assertEqual(len(drawn), 2)
        # leaving while dragging keeps it
        self.view.on_motion(area, FakeEvent(x, y))
        self.view._drag = (0, 0, 0, 0)
        self.view.on_leave(area, FakeEvent())
        self.assertIs(self.view.hover, self.node("vm"))

    def test_a_press_gets_the_focus(self):
        self.show(1000, 1000)
        focused = []
        self.patch(self.view.area, "grab_focus", lambda: focused.append(1))
        x, y = self.in_area(self.node("vm"))
        self.view.on_button_press(self.view.area, FakeEvent(x, y))
        self.view.on_button_press(self.view.area, FakeEvent(1, 1))
        self.assertEqual(len(focused), 2)

    def test_a_press_on_a_brick_is_the_tabs(self):
        self.show(1000, 1000)
        x, y = self.in_area(self.node("vm"))
        area = self.view.area
        self.assertFalse(self.view.on_button_press(area, FakeEvent(x, y)))
        self.assertFalse(
            self.view.on_button_press(area, FakeEvent(1, 1, button=3))
        )
        self.assertIsNone(self.view._drag)

    def test_the_brick_under_the_pointer(self):
        self.show(1000, 1000)
        x, y = self.in_area(self.node("vm"))
        area = self.view.area
        self.assertFalse(self.view.on_motion(area, FakeEvent(x, y)))
        self.assertIs(self.view.hover, self.node("vm"))
        self.view.on_motion(area, FakeEvent(1, 1))
        self.assertIsNone(self.view.hover)
        self.view.on_motion(area, FakeEvent(x, y))
        self.view.on_leave(area, FakeEvent())
        self.assertIsNone(self.view.hover)

    def test_the_tooltip(self):
        self.show(1000, 1000)
        x, y = self.in_area(self.node("vm"))
        tooltips = []

        class FakeTooltip:
            def set_text(self, text):
                tooltips.append(text)

        area = self.view.area
        self.assertTrue(
            self.view.on_query_tooltip(area, x, y, False, FakeTooltip())
        )
        self.assertFalse(
            self.view.on_query_tooltip(area, 1, 1, False, FakeTooltip())
        )
        self.assertEqual(tooltips, [tooltip_text(self.vm)])
        self.assertEqual(tooltip_text(self.vm), "vm · Qemu · off")

    def test_a_pinch(self):
        self.show(300, 200)
        self.view.zoom_to_100()

        class FakeGesture:
            def get_bounding_box_center(self):
                return True, 60.0, 40.0

        self.view.on_pinch_begin(FakeGesture(), None)
        self.view.on_pinch(FakeGesture(), 1.7)
        self.assertAlmostEqual(self.view.zoom, 1.7)
        self.assertFalse(self.view.fitting)
        self.view.on_pinch(FakeGesture(), 0.5)
        self.assertAlmostEqual(self.view.zoom, 0.5)

    def test_a_pinch_without_a_centre(self):
        self.show(300, 200)
        self.view.zoom_to_100()
        allocate(self.view, 300, 200)
        h, v = self.scroll()
        centre = self.view.to_layout(h + 150, v + 100)

        class FakeGesture:
            def get_bounding_box_center(self):
                return False, 0.0, 0.0

        self.view.on_pinch_begin(FakeGesture(), None)
        self.view.on_pinch(FakeGesture(), 2.0)
        allocate(self.view, 300, 200)
        h, v = self.scroll()
        x, y = self.view.to_layout(h + 150, v + 100)
        self.assertAlmostEqual(x, centre[0], delta=1)
        self.assertAlmostEqual(y, centre[1], delta=1)

    def test_the_signals(self):
        # connected to their handlers
        heard = []
        for name in (
            "on_draw",
            "on_area_allocated",
            "on_button_press",
            "on_button_release",
            "on_motion",
            "on_leave",
            "on_scroll",
            "on_key_press",
            "on_query_tooltip",
            "on_pinch_begin",
            "on_pinch",
        ):
            self.patch(
                TopologyView,
                name,
                lambda self, *args, name=name: heard.append(name),
            )
        view = TopologyView()
        self.addCleanup(view.destroy)
        area = view.area
        for signal, event_type in (
            ("button-press-event", Gdk.EventType.BUTTON_PRESS),
            ("button-release-event", Gdk.EventType.BUTTON_RELEASE),
            ("motion-notify-event", Gdk.EventType.MOTION_NOTIFY),
            ("leave-notify-event", Gdk.EventType.LEAVE_NOTIFY),
            ("scroll-event", Gdk.EventType.SCROLL),
            ("key-press-event", Gdk.EventType.KEY_PRESS),
        ):
            area.emit(signal, Gdk.Event.new(event_type))
        area.emit("query-tooltip", 1, 1, False, Gtk.Tooltip())
        area.emit(
            "draw",
            cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)),
        )
        view.pinch.emit("begin", None)
        view.pinch.emit("scale-changed", 1.5)
        allocate(view, 100, 100)
        self.assertEqual(
            set(heard),
            {
                "on_area_allocated",
                "on_button_press",
                "on_button_release",
                "on_motion",
                "on_leave",
                "on_scroll",
                "on_key_press",
                "on_query_tooltip",
                "on_draw",
                "on_pinch_begin",
                "on_pinch",
            },
        )
        events = area.get_events()
        for mask in (
            Gdk.EventMask.BUTTON_PRESS_MASK,
            Gdk.EventMask.BUTTON_RELEASE_MASK,
            Gdk.EventMask.POINTER_MOTION_MASK,
            Gdk.EventMask.SCROLL_MASK,
            Gdk.EventMask.SMOOTH_SCROLL_MASK,
            Gdk.EventMask.LEAVE_NOTIFY_MASK,
            Gdk.EventMask.KEY_PRESS_MASK,
        ):
            self.assertTrue(events & mask, mask)
        self.assertTrue(area.get_can_focus())
        self.assertTrue(area.get_has_tooltip())
        self.assertTrue(area.get_visible())
        self.assertTrue(area.get_style_context().has_class("view"))
