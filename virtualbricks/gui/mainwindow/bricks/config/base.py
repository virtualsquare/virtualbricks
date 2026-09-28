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
Code shared by the brick configuration panels.

Every panel subclasses ``ConfigController`` and implements ``build_ui()``,
that creates the widgets, and ``get_config_view()``, that returns the panel.
The helpers (``StateManager``, ``State``, ...) manage the sensitivity of the
widgets of the panels still without a draft.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from zope.interface import implementer

from virtualbricks.gui.interfaces import (
    IConfigController,
    IControl,
    IPrerequisite,
    IState,
    IStateManager,
)
from virtualbricks.i18n import _


@implementer(IConfigController)
class ConfigController:
    """
    Base class for the brick configuration panels.

    The panel returned by ``get_config_view()`` is shown in the main window
    together with the OK and Cancel buttons created by ``get_view()``.
    """

    def __init__(self, original):
        self.original = original
        self.build_ui()

    def on_ok_button_clicked(self, button, gui):
        self.configure_brick(gui)
        gui.curtain_down()

    def on_cancel_button_clicked(self, button, gui):
        gui.curtain_down()

    def get_view(self, gui):
        bbox = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        bbox.set_layout(Gtk.ButtonBoxStyle.END)
        bbox.set_spacing(5)
        ok_button = Gtk.Button.new_with_mnemonic(_("_OK"))
        ok_button.props.always_show_image = True
        ok_button.connect("clicked", self.on_ok_button_clicked, gui)
        bbox.add(ok_button)
        bbox.set_child_secondary(ok_button, False)
        cancel_button = Gtk.Button.new_with_mnemonic(_("_Cancel"))
        cancel_button.props.always_show_image = True
        cancel_button.connect("clicked", self.on_cancel_button_clicked, gui)
        bbox.add(cancel_button)
        bbox.set_child_secondary(cancel_button, True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_end(bbox, False, True, 0)
        box.pack_end(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
            False,
            False,
            3,
        )
        box.show_all()
        box.pack_start(self.get_config_view(gui), True, True, 0)
        return box


# Widget sensitivity management, used by the configuration panels and by the
# main window.

NO, MAYBE, YES = range(3)


@implementer(IPrerequisite)
class CompoundPrerequisite:

    def __init__(self, *prerequisites):
        self.prerequisites = list(prerequisites)

    def add_prerequisite(self, prerequisite):
        self.prerequisites.append(prerequisite)

    def __call__(self):
        for prerequisite in self.prerequisites:
            satisfied = prerequisite()
            if satisfied in (YES, NO):
                return satisfied
        return MAYBE


@implementer(IState)
class State:

    def __init__(self):
        self.prerequisite = CompoundPrerequisite()
        self.controls = []

    def add_prerequisite(self, prerequisite):
        self.prerequisite.add_prerequisite(prerequisite)

    def add_control(self, control):
        self.controls.append(control)

    def check(self):
        enable = self.prerequisite()
        for control in self.controls:
            control.react(enable)


@implementer(IControl)
class SensitiveControl:

    def __init__(self, widget, tooltip=None):
        self.widget = widget
        self.tooltip = tooltip

    def react(self, enable):
        self.set_sensitive(enable)

    def set_sensitive(self, sensitive):
        if self.widget.get_sensitive() ^ sensitive:
            self.widget.set_sensitive(sensitive)
            tooltip = self.tooltip
            self.tooltip = self.widget.get_tooltip_markup()
            # In Gtk3 seems that None value to set_tooltip_markup is
            # valid, but it breaks
            if tooltip is None:
                tooltip = ""
            self.widget.set_tooltip_markup(tooltip)


@implementer(IControl)
class InsensitiveControl:

    def __init__(self, widget, tooltip=None):
        self.widget = widget
        self.tooltip = widget.get_tooltip_markup()
        widget.set_tooltip_markup(tooltip)

    def react(self, enable):
        disable = not enable
        if self.widget.get_sensitive() ^ disable:
            self.widget.set_sensitive(disable)
            tooltip = self.tooltip
            self.tooltip = self.widget.get_tooltip_markup()
            self.widget.set_tooltip_markup(tooltip)


@implementer(IControl)
class ActiveControl:

    def __init__(self, widget):
        self.widget = widget

    def react(self, enable):
        if not enable:
            self.widget.set_active(False)


@implementer(IStateManager)
class StateManager:

    control_factory = SensitiveControl

    def __init__(self):
        self.states = []

    def add_state(self, state):
        self.states.append(state)

    def _build_state(self, tooltip, *widgets):
        state = State()
        for widget in widgets:
            state.add_control(self.control_factory(widget, tooltip))
        self.add_state(state)
        return state

    def _add_checkbutton(
        self, checkbutton, prerequisite, tooltip=None, *widgets
    ):
        state = self._build_state(tooltip, *widgets)
        state.add_prerequisite(prerequisite)
        checkbutton.connect("toggled", lambda cb: state.check())
        state.check()
        return state

    def add_checkbutton_active(self, checkbutton, tooltip=None, *widgets):
        return self._add_checkbutton(
            checkbutton, checkbutton.get_active, tooltip, *widgets
        )

    def add_checkbutton_not_active(self, checkbutton, tooltip=None, *widgets):
        return self._add_checkbutton(
            checkbutton,
            lambda: not checkbutton.get_active(),
            tooltip,
            *widgets,
        )
