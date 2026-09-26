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
The Topology tab: when it lays the lab out, its bar and menu, the clicks
on the bricks, and the export.
"""

from virtualbricks import topology as layouts
from virtualbricks.config import projects
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import GuiTestCase, has_display

if has_display:
    from gi.repository import Gdk, GLib, Gtk

    from virtualbricks.gui.mainwindow import picture, topology
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

        def layout(bricks, direction, measure):
            # the names measured by the view
            self.assertEqual(measure, self.view.measure)
            self.laid_out.append(([b.name for b in bricks], direction))
            return layouts.layout(bricks, direction, measure)

        self.patch(topology, "layout", layout)
        self.sw1 = self.factory.new_brick("switch", "sw1")
        self.vm = self.factory.new_brick("qemu", "vm")
        self.vm.connect(self.sw1.socks[0])
        self.gui = FakeGui()
        self.tab = TopologyTab(self.gui, self.factory)
        self.addCleanup(self.tab.destroy)
        self.view = self.tab.view

    def show(self, width=600, height=400):
        self.tab.on_shown()
        allocate(self.tab, width, height)
        run_idle_calls()
        allocate(self.tab, width, height)

    def in_area(self, brick):
        node = next(n for n in self.view.layout.nodes if n.brick is brick)
        ox, oy = self.view.origin()
        zoom = self.view.zoom
        return ox + node.x * zoom, oy + node.y * zoom


class TestLayingOut(TopologyTestCase):

    def test_when_it_shows(self):
        self.factory.new_brick("switch", "sw0")
        self.assertEqual(self.laid_out, [])
        self.factory.del_brick(self.factory.get_brick_by_name("sw0"))
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
        self.tab.direction_action.change_state(GLib.Variant.new_string("TB"))
        self.assertEqual(self.laid_out[-1], (["sw1", "vm"], "TB"))
        self.assertEqual(
            self.tab.direction_action.get_state().get_string(), "TB"
        )
        # hidden, it waits
        self.tab.on_left()
        self.tab.direction_action.change_state(GLib.Variant.new_string("LR"))
        self.assertEqual(len(self.laid_out), 2)
        self.tab.on_shown()
        self.assertEqual(self.laid_out[-1], (["sw1", "vm"], "LR"))


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
            self.factory.del_brick(brick)
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
            self.factory.del_brick(brick)
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
        self.assertEqual(tab.level_button.get_tooltip_text(), "Zoom to 100%")
        self.assertEqual(
            tab.level_button.get_accessible().get_name(), "Zoom to 100%"
        )

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
                        ("Left to Right", "topology.direction", "LR", None),
                        ("Top to Bottom", "topology.direction", "TB", None),
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
        self.assertEqual(sorted(group.list_actions()), ["direction", "export"])
        self.assertEqual(
            group.get_action_state("direction").get_string(), "LR"
        )


class TestClicks(TopologyTestCase):

    def setUp(self):
        super().setUp()
        self.menus = []
        self.patch(
            topology, "IMenu", lambda brick, _: FakeMenu(self.menus, brick)
        )
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
        self.assertEqual(self.menus, [(self.vm, 3, self.gui)])

    def test_a_double_click_starts_or_stops(self):
        self.assertTrue(self.press(self.vm, double=True))
        self.assertEqual(self.gui.started, [self.vm])
        # one click does nothing
        self.assertTrue(self.press(self.vm))
        self.assertEqual(self.gui.started, [self.vm])

    def test_not_on_a_brick(self):
        event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
        event.button.button = 3
        event.button.x = event.button.y = 1
        self.assertFalse(self.tab.on_button_press(self.view.area, event))
        self.assertEqual(self.menus, [])


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
            self.factory.del_brick(brick)
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
