# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_bricks -*-
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
The Bricks tab of the main window: the bricks of the project.

A row above the list holds New Brick, the search, a switch between all the
bricks and the running ones, how many run, and Start All and Stop All. The
list, of :mod:`virtualbricks.gui.mainwindow.bricklist`, has a row per brick
with its own buttons; a project without bricks shows a page that says what a
brick is instead.

In the list, the right button, the Menu key and Shift+F10 open the menu of
the selected brick, Delete removes it and F2 renames it; Ctrl+F goes to the
search, and so does typing in the list; Escape clears the search.

A double click or Enter configures a brick, as Configure in its menu does:
its settings take the place of the list, under a line that names the brick,
with the panel of :mod:`virtualbricks.gui.windows` in a scrolled window and
Cancel and OK under it. The menus and the other tabs stay. Cancel, OK and
Escape go back to the list; so do deleting the brick, opening another
project and configuring another brick, as Cancel.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402
from twisted.internet import defer  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks.gui import graphics  # noqa: E402
from virtualbricks.gui.interfaces import IConfigController  # noqa: E402
from virtualbricks.gui.mainwindow import (  # noqa: E402
    brickinfo,
    bricklist,
    brickmenu,
)
from virtualbricks.gui.mainwindow.brickinfo import State  # noqa: E402
from virtualbricks.gui.mainwindow.bricklist import BrickList  # noqa: E402
from virtualbricks.gui.mainwindow.tab import Tab  # noqa: E402
from virtualbricks.gui.windows.base import pango_attr_list  # noqa: E402
from virtualbricks.gui.windows.newbrick import NewBrickDialog  # noqa: E402
from virtualbricks.i18n import _, ngettext  # noqa: E402
from virtualbricks.tools import dispose, is_running  # noqa: E402

logger = Logger()
not_started = "Brick not started."
not_stopped = "Brick not stopped."

# The factory's signals after which the row above the list, and the page
# shown, say again what they say.
SIGNALS = ("brick-added", "brick-removed", "brick-changed")
# Between the controls, and around them, in pixels.
GAP = 8
EMPTY_ICON_SIZE = 64
EMPTY_ICON_OPACITY = 0.35


def _icon_button(label, icon):
    return Gtk.Button(
        visible=True,
        label=label,
        image=Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON),
        always_show_image=True,
    )


def empty_icon():
    """A switch, grey: the picture of a project without bricks."""

    filename = graphics.get_data_filename("switch.png")
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            filename, EMPTY_ICON_SIZE, EMPTY_ICON_SIZE
        )
    except GLib.Error:
        return None
    grey = pixbuf.copy()
    pixbuf.saturate_and_pixelate(grey, 0.0, False)
    return grey


def types(event) -> bool:
    """Whether a key typed in the list goes to the search: a character."""

    modifiers = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK
    if event.state & modifiers:
        return False
    return chr(Gdk.keyval_to_unicode(event.keyval)).isprintable()


def count(bricks) -> str:
    """How many bricks run, of how many."""

    total = len(bricks)
    running = sum(1 for brick in bricks if is_running(brick))
    return ngettext(
        "{running} of {total} running", "{running} of {total} running", total
    ).format(running=running, total=total)


class BricksTab(Tab, Gtk.Stack):
    """The bricks of the project, and what can be done with them."""

    title = _("_Bricks")

    def __init__(self, gui, factory) -> None:
        super().__init__(visible=True)
        self.gui = gui
        self.factory = factory
        self._menu: Gtk.Menu | None = None
        # the brick whose settings show, and their panel
        self.configuring = None
        self._controller = None
        self.settings: Gtk.Box | None = None
        self.bricks_page = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL
        )
        self.add_named(self.bricks_page, "bricks")

        header = Gtk.Box(visible=True, spacing=GAP, margin=GAP)
        self.new_button = _icon_button(_("New Brick"), "list-add-symbolic")
        self.search = Gtk.SearchEntry(
            visible=True, placeholder_text=_("Search bricks"), width_chars=24
        )
        self.all_button = Gtk.RadioButton(
            visible=True, label=_("All"), draw_indicator=False
        )
        self.running_button = Gtk.RadioButton(
            visible=True,
            label=_("Running"),
            draw_indicator=False,
            group=self.all_button,
        )
        filters = Gtk.Box(visible=True)
        filters.get_style_context().add_class("linked")
        filters.pack_start(self.all_button, False, False, 0)
        filters.pack_start(self.running_button, False, False, 0)
        self.count = Gtk.Label(visible=True)
        self.count.get_style_context().add_class("dim-label")
        self.start_button = _icon_button(
            _("Start All"), "media-playback-start-symbolic"
        )
        self.stop_button = _icon_button(
            _("Stop All"), "media-playback-stop-symbolic"
        )
        all_bricks = Gtk.Box(visible=True)
        all_bricks.get_style_context().add_class("linked")
        all_bricks.pack_start(self.start_button, False, False, 0)
        all_bricks.pack_start(self.stop_button, False, False, 0)
        for widget in (self.new_button, self.search, filters):
            header.pack_start(widget, False, False, 0)
        header.pack_end(all_bricks, False, False, 0)
        header.pack_end(self.count, False, False, 0)
        self.bricks_page.pack_start(header, False, False, 0)
        self.bricks_page.pack_start(
            Gtk.Separator(
                visible=True, orientation=Gtk.Orientation.HORIZONTAL
            ),
            False,
            False,
            0,
        )

        self.list = BrickList(gui, factory)
        scrolled = Gtk.ScrolledWindow(
            visible=True, hscrollbar_policy=Gtk.PolicyType.NEVER
        )
        scrolled.add(self.list)
        self.empty = self._empty_page()
        self.pages = Gtk.Stack(visible=True)
        self.pages.add_named(scrolled, "list")
        self.pages.add_named(self.empty, "empty")
        self.bricks_page.pack_start(self.pages, True, True, 0)

        self.new_button.connect("clicked", self.on_new_clicked)
        self.empty_new_button.connect("clicked", self.on_new_clicked)
        self.start_button.connect("clicked", self.on_start_clicked)
        self.stop_button.connect("clicked", self.on_stop_clicked)
        self.search.connect("search-changed", self.on_search_changed)
        self.search.connect("stop-search", self.on_stop_search)
        self.running_button.connect("toggled", self.on_running_toggled)
        self.list.connect("button-press-event", self.on_button_press)
        self.list.connect("key-press-event", self.on_list_key_press)
        self.list.connect("row-activated", self.on_row_activated)
        self.connect("key-press-event", self.on_key_press)
        for signal in SIGNALS:
            factory.connect(signal, self.on_brick_changed)
        factory.connect("brick-removed", self.on_brick_removed)
        self.update()

    def _empty_page(self) -> Gtk.Box:
        page = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=GAP,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            margin=3 * GAP,
        )
        image = Gtk.Image(visible=True, pixel_size=EMPTY_ICON_SIZE)
        icon = empty_icon()
        if icon is not None:
            image.set_from_pixbuf(icon)
        image.set_opacity(EMPTY_ICON_OPACITY)
        title = Gtk.Label(
            visible=True,
            label=_("No Bricks Yet"),
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
                Pango.attr_scale_new(1.3),
            ),
        )
        words = Gtk.Label(
            visible=True,
            label=_(
                "A brick is a switch, a virtual machine, a wire or a tap. "
                "Add the first one to start the lab."
            ),
            wrap=True,
            max_width_chars=40,
            justify=Gtk.Justification.CENTER,
        )
        words.get_style_context().add_class("dim-label")
        self.empty_new_button = Gtk.Button(
            visible=True, label=_("New Brick"), halign=Gtk.Align.CENTER
        )
        self.empty_new_button.get_style_context().add_class("suggested-action")
        for widget in (image, title, words, self.empty_new_button):
            page.pack_start(widget, False, False, 0)
        return page

    def update(self) -> None:
        """The row above the list, and the page, for the bricks there are."""

        bricks = self.factory.bricks
        states = [brickinfo.state(brick) for brick in bricks]
        self.pages.set_visible_child_name("list" if bricks else "empty")
        self.count.set_text(count(bricks) if bricks else "")
        for widget in (self.search, self.all_button, self.running_button):
            widget.set_sensitive(bool(bricks))
        self.start_button.set_sensitive(State.STOPPED in states)
        self.stop_button.set_sensitive(State.RUNNING in states)

    def start_all(self) -> defer.Deferred:
        """Start the bricks that can start; the failures are logged."""

        deferreds = [
            brick.poweron()
            for brick in self.factory.bricks
            if brickinfo.state(brick) is State.STOPPED
        ]
        return self._log_failures(deferreds, not_started)

    def stop_all(self) -> defer.Deferred:
        """Stop the running bricks; the failures are logged."""

        deferreds = [
            defer.maybeDeferred(brick.poweroff)
            for brick in self.factory.bricks
            if is_running(brick)
        ]
        return self._log_failures(deferreds, not_stopped)

    @staticmethod
    def _log_failures(deferreds, message) -> defer.Deferred:
        def done(results):
            for success, value in results:
                if not success:
                    logger.failure(message, value)

        return defer.DeferredList(deferreds, consumeErrors=True).addCallback(
            done
        )

    def open_menu(self, event=None) -> None:
        """
        Open the menu of the selected brick: at the pointer for a click, under
        its button for the Menu key.
        """

        brick = self.list.selected_brick()
        if brick is None:
            return
        if event is None:
            widget = self.list.row_of(brick).menu_button
        else:
            widget = self.list
        # kept while it shows
        self._menu = brickmenu.popup(widget, event, self.gui, brick, True)

    # The settings of a brick

    def configure(self, brick) -> None:
        """
        Show the settings of brick in place of the list. Those of another
        brick close first, as with Cancel. A brick without a panel, as a
        router, shows nothing.
        """

        controller = IConfigController(brick, None)
        if controller is None:
            return
        if self.configuring is not None:
            self.cancel_settings()
        self.configuring = brick
        self._controller = controller
        self.settings = self._settings_page(brick, controller)
        self.add_named(self.settings, "settings")
        self.set_visible_child(self.settings)

    def _settings_page(self, brick, controller) -> Gtk.Box:
        page = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        head = Gtk.Box(visible=True, spacing=12, margin=GAP)
        image = Gtk.Image(visible=True, pixel_size=bricklist.ICON_SIZE)
        pixbuf = self.list.icons.get(brick, is_running(brick))
        if pixbuf is not None:
            image.set_from_pixbuf(pixbuf)
        text = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(
            visible=True,
            xalign=0.0,
            label=brick.get_name(),
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD)
            ),
        )
        kind = Gtk.Label(
            visible=True,
            xalign=0.0,
            label=_("{kind} settings").format(kind=brickinfo.kind(brick)),
        )
        kind.get_style_context().add_class("dim-label")
        text.pack_start(name, False, False, 0)
        text.pack_start(kind, False, False, 0)
        head.pack_start(image, False, False, 0)
        head.pack_start(text, True, True, 0)

        scrolled = Gtk.ScrolledWindow(visible=True)
        # in a box, as get_view() puts it: the virtual machine's panel
        # replaces itself in its parent once it knows the QEMU there is
        holder = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            margin_start=GAP,
            margin_end=GAP,
            margin_top=GAP,
        )
        panel = controller.get_config_view(self.gui)
        panel.show()
        holder.pack_start(panel, True, True, 0)
        scrolled.add(holder)

        actions = Gtk.Box(visible=True, spacing=GAP, margin=GAP)
        self.cancel_button = Gtk.Button.new_with_mnemonic(_("_Cancel"))
        self.ok_button = Gtk.Button.new_with_mnemonic(_("_OK"))
        self.ok_button.get_style_context().add_class("suggested-action")
        self.cancel_button.show()
        self.ok_button.show()
        actions.pack_start(self.cancel_button, False, False, 0)
        actions.pack_end(self.ok_button, False, False, 0)
        # the panel's own: they call the window's curtain_down()
        self.cancel_button.connect(
            "clicked", controller.on_cancel_button_clicked, self.gui
        )
        self.ok_button.connect(
            "clicked", controller.on_ok_button_clicked, self.gui
        )

        for widget, expand in (
            (head, False),
            (Gtk.Separator(visible=True), False),
            (scrolled, True),
            (Gtk.Separator(visible=True), False),
            (actions, False),
        ):
            page.pack_start(widget, expand, expand, 0)
        page.connect("key-press-event", self.on_settings_key_press)
        return page

    def cancel_settings(self) -> None:
        """Close the settings, as Cancel does."""

        dispose(self._controller)
        self.close_settings()

    def close_settings(self) -> None:
        """Back to the list, on the brick configured."""

        brick = self.configuring
        if brick is None:
            return
        self.configuring = self._controller = None
        # the stack shows the list once the page goes
        self.settings.destroy()
        self.settings = None
        row = self.list.row_of(brick)
        if row is not None:
            self.list.select_row(row)
            row.grab_focus()

    # What the main window tells

    def on_open(self) -> None:
        if self.configuring is not None:
            self.cancel_settings()
        # an entry emptied tells the list at once
        self.search.set_text("")
        self.all_button.set_active(True)

    def on_quit(self) -> None:
        self.list.close()
        for signal in SIGNALS:
            self.factory.disconnect(signal, self.on_brick_changed)
        self.factory.disconnect("brick-removed", self.on_brick_removed)

    # Signals

    def on_brick_changed(self, brick) -> None:
        self.update()

    def on_brick_removed(self, brick) -> None:
        if brick is self.configuring:
            self.cancel_settings()

    def on_settings_key_press(self, page, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.cancel_settings()
            return True
        return False

    def on_new_clicked(self, button) -> None:
        NewBrickDialog(self.factory).show(self.gui.window)

    def on_start_clicked(self, button) -> None:
        self.start_all()

    def on_stop_clicked(self, button) -> None:
        self.stop_all()

    def on_search_changed(self, entry) -> None:
        self.list.set_search(entry.get_text())

    def on_stop_search(self, entry) -> None:
        entry.set_text("")
        # back to the list, on the selected brick or the first
        row = self.list.get_selected_row() or self.list.get_row_at_index(0)
        if row is not None:
            row.grab_focus()

    def on_running_toggled(self, button) -> None:
        self.list.set_only_running(button.get_active())

    def on_row_activated(self, listbox, row) -> None:
        self.gui.curtain_up(row.brick)

    def on_button_press(self, listbox, event) -> bool:
        if not event.triggers_context_menu():
            return False
        row = listbox.get_row_at_y(int(event.y))
        if row is None:
            return False
        listbox.select_row(row)
        row.grab_focus()
        self.open_menu(event)
        return True

    def on_list_key_press(self, listbox, event) -> bool:
        keyval = event.keyval
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        brick = listbox.selected_brick()
        if keyval == Gdk.KEY_Menu or (keyval == Gdk.KEY_F10 and shift):
            self.open_menu()
            return True
        if brick is not None and keyval in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete):
            self.gui.ask_remove_brick(brick)
            return True
        if brick is not None and keyval == Gdk.KEY_F2:
            actions = listbox.row_of(brick).actions
            if actions.get_action_enabled("rename"):
                actions.activate_action("rename", None)
            return True
        if keyval == Gdk.KEY_Escape and self.search.get_text():
            self.on_stop_search(self.search)
            return True
        # typing searches
        if types(event) and self.search.get_sensitive():
            if self.search.handle_event(event):
                self.search.grab_focus_without_selecting()
                return True
        return False

    def on_key_press(self, tab, event) -> bool:
        control = event.state & Gdk.ModifierType.CONTROL_MASK
        if self.configuring is not None:
            return False
        if control and event.keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search.grab_focus()
            return True
        return False
