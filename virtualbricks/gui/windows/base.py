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
Code shared by the windows that build their UI in Python.

Every window subclasses ``_Window``, ``_Dialog`` or ``Window`` (brick
configuration panels subclass ``ConfigController``) and implements
``build_ui()``, that creates the widgets, and ``get_root_widget()``, that
returns the main widget.

The helpers (``StateManager``, ``_PlugMixin``, ...) manage the sensitivity of
the widgets and the plugs of the brick configuration panels.
"""

import functools
import gettext
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk, Pango
from zope.interface import implementer

from virtualbricks.config import settings
from virtualbricks.gui import graphics
from virtualbricks.gui.interfaces import (
    IConfigController,
    IControl,
    IPrerequisite,
    IState,
    IStateManager,
)
from virtualbricks.tools import dispose

TRANSLATION_DOMAIN = "virtualbricks"


def _(message: str) -> str:
    """
    Translate ``message``.

    Gtk.Builder used this translation domain for the strings marked as
    translatable in the Glade files.
    """

    return gettext.dgettext(TRANSLATION_DOMAIN, message)


def load_pixbuf(name: str) -> GdkPixbuf.Pixbuf:
    """
    Load an image from the ``virtualbricks/gui/data`` directory, the same
    directory Gtk.Builder used to resolve the image paths of the Glade files.
    """

    return GdkPixbuf.Pixbuf.new_from_file(graphics.get_image(name))


def pango_attr_list(*attributes: Pango.Attribute) -> Pango.AttrList:
    """Return a Pango.AttrList with the given attributes."""

    attr_list = Pango.AttrList()
    for attribute in attributes:
        attr_list.insert(attribute)
    return attr_list


def destroy_on_exit(func: Callable) -> Callable:
    @functools.wraps(func)
    def on_response(self, dialog, *args):
        try:
            return func(self, dialog, *args)
        finally:
            dialog.destroy()

    return on_response


def iter_tree_model(tree_model):
    """
    :type disk_image: virtualbricks.virtualmachines.Image
    :rtype: Generator[Tuple[Any, Gtk.TreeIter]]
    """

    itr = tree_model.get_iter_first()
    while itr:
        value = tree_model.get_value(itr, 0)
        yield value, itr
        itr = tree_model.iter_next(itr)


NUMERIC = set(map(str, range(10)))
NUMPAD = set(map(lambda i: "KP_%d" % i, range(10)))
EXTRA = set(["BackSpace", "Delete", "Left", "Right", "Home", "End", "Tab"])
VALIDKEY = NUMERIC | NUMPAD | EXTRA


class _Window:
    """Base class for all windows."""

    on_destroy = None

    def show(self):
        window = self.get_root_widget()
        if self.on_destroy is not None:
            window.connect("destroy", lambda w: self.on_destroy())
        window.show()


class _Dialog(_Window):

    def show(self, parent=None):
        if parent is not None:
            self.get_root_widget().set_transient_for(parent)
        super().show()


class Window:
    """
    Base class for the dialogs that used ``virtualbricks.gui.dialogs.Window``.

    The UI is built when the instance is created.
    """

    on_destroy = None

    def __init__(self):
        self.build_ui()

    def set_transient_for(self, parent):
        self.get_root_widget().set_transient_for(parent)

    def show(self, parent=None):
        window = self.get_root_widget()
        if parent is not None:
            window.set_transient_for(parent)
        window.connect("destroy", self.on_window_destroy)
        if self.on_destroy is not None:
            window.connect("destroy", lambda w: self.on_destroy())
        window.show()

    def on_window_destroy(self, window):
        dispose(self)

    def __dispose__(self):
        pass


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

    def __dispose__(self):
        pass

    def on_ok_button_clicked(self, button, gui):
        self.configure_brick(gui)
        dispose(self)
        gui.curtain_down()

    def on_cancel_button_clicked(self, button, gui):
        dispose(self)
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


# Plug configuration, used by the panels of the bricks with plugs.


def _sock_should_visible(model, iter, data):
    sock = model.get_value(iter, 0)
    return sock and (
        sock.brick.get_type().startswith("Switch")
        or settings.get("femaleplugs")
    )


def _set_text(column, cell_renderer, model, itr):
    sock = model.get_value(itr, 0)
    cell_renderer.set_property("text", sock.nickname)


class _PlugMixin:

    def configure_sock_combobox(self, combo, model, brick, plug, gui):
        filtered_model = model.filter_new()
        filtered_model.set_visible_func(_sock_should_visible)
        combo.set_model(filtered_model)
        cell = combo.get_cells()[0]
        combo.set_cell_data_func(cell, _set_text)
        if plug.configured():
            itr = filtered_model.get_iter_first()
            while itr:
                if filtered_model[itr][0] is plug.sock:
                    combo.set_active_iter(itr)
                    break
                itr = filtered_model.iter_next(itr)

    def connect_plug(self, plug, combo):
        itr = combo.get_active_iter()
        if itr:
            model = combo.get_model()
            plug.connect(model[itr][0])
