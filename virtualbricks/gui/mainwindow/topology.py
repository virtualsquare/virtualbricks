# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_topology -*-
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
The Topology tab of the main window: the bricks and their connections.

Graphviz draws the picture when the tab shows, again after a brick changes,
and it can be saved as an image. A click on a brick in the picture works as
in the list of the bricks: the right button opens its menu, a double click
starts or stops it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks.gui import graphics  # noqa: E402
from virtualbricks.gui.interfaces import IMenu  # noqa: E402
from virtualbricks.gui.mainwindow.tab import Tab  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

logger = Logger()
drawing_topology = "drawing topology"
top_invalid_format = "Error saving topology: Invalid image format"
top_write_error = "Error saving topology: Could not write file"
top_unknown = "Error saving topology: Unknown error"

# The signals of the factory after which the picture is drawn again.
BRICK_SIGNALS = ("brick-changed", "brick-added", "brick-removed")


class TopologyTab(Tab, Gtk.Box):
    """The picture of the bricks of the project and how they connect."""

    title = _("_Topology")

    def __init__(self, gui, factory) -> None:
        super().__init__(visible=True, orientation=Gtk.Orientation.VERTICAL)
        self.gui = gui
        self.factory = factory
        # the picture drawn last, a graphics.Topology
        self.topology = None
        self._shown = False
        self._should_draw = True

        buttons = Gtk.Box(visible=True)
        self.export_button = Gtk.Button(visible=True)
        export = Gtk.Box(visible=True)
        export.pack_start(
            Gtk.Image(visible=True, stock="gtk-save-as"), True, True, 0
        )
        export.pack_start(
            Gtk.Label(visible=True, label=_("Export as Image")), True, True, 0
        )
        self.export_button.add(export)
        buttons.pack_start(self.export_button, False, True, 0)
        self.horizontal_radio = Gtk.RadioButton(
            label=_("Expand Horizontally"), visible=True, active=True
        )
        buttons.pack_start(self.horizontal_radio, False, True, 0)
        self.vertical_radio = Gtk.RadioButton(
            label=_("Expand Vertically"),
            visible=True,
            group=self.horizontal_radio,
        )
        buttons.pack_start(self.vertical_radio, False, True, 0)
        self.pack_start(buttons, False, True, 0)
        self.scrolled = Gtk.ScrolledWindow(
            visible=True, shadow_type=Gtk.ShadowType.IN
        )
        self.viewport = Gtk.Viewport(visible=True)
        self.image = Gtk.Image(
            visible=True, xalign=0, yalign=0, stock="gtk-missing-image"
        )
        self.viewport.add(self.image)
        self.scrolled.add(self.viewport)
        self.pack_start(self.scrolled, True, True, 0)

        self.export_button.connect("clicked", self.on_export_clicked)
        # the other radio button goes off
        self.horizontal_radio.connect("toggled", self.on_orientation_toggled)
        self.viewport.connect("button-press-event", self.on_button_press)
        self.scrolled.get_hadjustment().connect(
            "value-changed", self.on_h_scrolled
        )
        self.scrolled.get_vadjustment().connect(
            "value-changed", self.on_v_scrolled
        )
        for signal in BRICK_SIGNALS:
            factory.connect(signal, self.on_brick_changed)

    def draw(self) -> None:
        """Draw the picture now if the tab shows, else when it shows."""

        if self._shown:
            self._draw()
        else:
            self._should_draw = True

    def _draw(self) -> None:
        logger.debug(drawing_topology)
        orientation = "TB" if self.vertical_radio.get_active() else "LR"
        self.topology = graphics.Topology(
            self.image,
            self.factory.bricks,
            1.00,
            orientation,
            self.factory.runtime_dir,
        )
        self._should_draw = False

    def _draw_if_needed(self) -> None:
        if self._should_draw:
            self._draw()

    def brick_at(self, x, y):
        """The brick drawn at x, y of the picture, or None."""

        self._draw_if_needed()
        for node in self.topology.nodes:
            if node.here(x, y):
                return self.factory.get_brick_by_name(node.name)
        return None

    def export(self, filename) -> None:
        """Save the picture in an image file, of the type of its name."""

        try:
            self._draw_if_needed()
            self.topology.export(filename)
        except KeyError:
            logger.failure(top_invalid_format)
        except IOError:
            logger.failure(top_write_error)
        except Exception:
            logger.failure(top_unknown)

    # What the main window tells

    def on_shown(self) -> None:
        self._shown = True
        self._draw_if_needed()

    def on_left(self) -> None:
        self._shown = False

    def on_quit(self) -> None:
        for signal in BRICK_SIGNALS:
            self.factory.disconnect(signal, self.on_brick_changed)

    # Signals

    def on_brick_changed(self, brick) -> None:
        self.draw()

    def on_orientation_toggled(self, button) -> None:
        self._draw()

    def on_export_clicked(self, button) -> None:
        chooser = Gtk.FileChooserDialog(
            title=_("Select an image file"),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(
                "_Cancel",
                Gtk.ResponseType.CANCEL,
                "_Save",
                Gtk.ResponseType.OK,
            ),
        )
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect("response", self.on_export_response)
        chooser.show()

    def on_export_response(self, dialog, response_id) -> None:
        try:
            if response_id == Gtk.ResponseType.OK:
                self.export(dialog.get_filename())
        finally:
            dialog.destroy()

    def on_button_press(self, viewport, event) -> bool | None:
        brick = self.brick_at(*event.get_coords())
        if brick is None:
            return None
        if event.button == 3:
            IMenu(brick, None).popup(event.button, event.time, self.gui)
        elif event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
            self.gui.startstop_brick(brick)
        return True

    def on_h_scrolled(self, adjustment) -> None:
        if self.topology is not None:
            self.topology.x_adj = adjustment.get_value()

    def on_v_scrolled(self, adjustment) -> None:
        if self.topology is not None:
            self.topology.y_adj = adjustment.get_value()
