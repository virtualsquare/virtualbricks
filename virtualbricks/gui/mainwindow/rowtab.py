# -*- test-case-name: virtualbricks.tests.gui.mainwindow.test_rowtab -*-
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
What the Bricks and the Events tabs share: a row for each object of the
project, a brick or an event.

``RowsTab`` has two pages. The first has a row of controls over the list:
New, the search, a switch between all the objects and the running ones, how
many run, and Start All and Stop All; under them, the ``RowList``, or a page
that says what the objects are when the project has none. The second has the
settings of one object: a line that names it, its panel in a scrolled
window, and Cancel and OK. The panel, of
:mod:`virtualbricks.gui.mainwindow.bricks.config.panel`, is on a draft: an
info bar over it while its object runs, and OK only while the draft has no
errors, the first of them beside it; OK applies the draft.

A ``Row`` shows an object's icon, grey while it doesn't run; its name; a line
about it; its state; a button that starts or stops it; and the button of its
menu. The list has a row per object, in their order, follows the factory,
and keeps the objects whose name or kind has the text of the search.

In the list, the right button, the Menu key and Shift+F10 open the menu of
the selected object, Delete and F2 do what the menu's items of those keys
do, and nothing while the items are greyed; Ctrl+F goes to the
search, and so does typing in the list; Escape clears the search. A double
click or Enter configures an object. Cancel, OK and Escape leave the
settings; so do deleting the object, opening another project and configuring
another object, as Cancel.

Each tab says what differs: its words, its rows, its menu, how its objects
start and stop, what New does, and their panels. A kind of object that
doesn't start or stop, as the disk images, has no Start or Stop: the switch
shows the objects in use, as the list says which are.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402
from twisted.internet import defer  # noqa: E402

from virtualbricks.gui import graphics  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.config.panel import (
    Panel,
)  # noqa: E402
from virtualbricks.gui.mainwindow.picture import greyed  # noqa: E402
from virtualbricks.gui.mainwindow.tab import (  # noqa: E402
    MenuActions,
    Tab,
    icon_button,
)
from virtualbricks.gui.pango import pango_attr_list  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from twisted.logger import Logger
    from twisted.python.failure import Failure

    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.bricks import Brick
    from virtualbricks.bricks.event import Event
    from virtualbricks.bricks.virtualmachine import Image
    from virtualbricks.gui.mainwindow.window import VBGUI
    from virtualbricks.observable import Signal

# The objects of a tab: bricks, events or disk images.
T = TypeVar("T", bound="Brick | Event | Image")
T_contra = TypeVar("T_contra", contravariant=True)
W = TypeVar("W", bound=Gtk.Widget)

ICON_SIZE = 32
# A stopped object's icon, this opaque.
STOPPED_OPACITY = 0.55
# Between the controls, and around them, in pixels.
GAP = 8
EMPTY_ICON_SIZE = 64
EMPTY_ICON_OPACITY = 0.35
# The colours of the dot of a running object, by what running means.
DOTS = ("running", "waiting")

_css = Gtk.CssProvider()
_css.load_from_data(b"""
    .state-dot {
        min-width: 8px;
        min-height: 8px;
        border-radius: 4px;
        background-color: alpha(currentColor, 0.4);
    }
    .state-dot.running { background-color: #33d17a; }
    .state-dot.waiting { background-color: #3584e4; }
    .state-warning { color: #e5a50a; }
    """)


class Pictures(Protocol[T_contra]):
    """What gives the picture of an object, running or not."""

    def get(
        self, item: T_contra, running: bool, /
    ) -> GdkPixbuf.Pixbuf | None: ...


def styled(widget: W, *classes: str) -> W:
    context = widget.get_style_context()
    context.add_provider(_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    for name in classes:
        context.add_class(name)
    return widget


def _icon_button(label: str, icon: str) -> Gtk.Button:
    return Gtk.Button(
        visible=True,
        label=label,
        image=Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON),
        always_show_image=True,
    )


def empty_icon(name: str) -> GdkPixbuf.Pixbuf | None:
    """The picture of a project without objects: an icon, grey."""

    filename = graphics.icon_file(name)
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            filename, EMPTY_ICON_SIZE, EMPTY_ICON_SIZE
        )
    except GLib.Error:
        return None
    assert pixbuf is not None, "a file that can't be read raises GLib.Error"
    return greyed(pixbuf)


def theme_icon(
    names: Iterable[str], size: int, grey: bool = False
) -> GdkPixbuf.Pixbuf | None:
    """The first of the icon names that the theme has, at size; grey."""

    theme = Gtk.IconTheme.get_default()
    for name in names:
        try:
            pixbuf = theme.load_icon(
                name, size, Gtk.IconLookupFlags.FORCE_SIZE
            )
        except GLib.Error:
            continue
        if pixbuf is None:
            continue
        if grey:
            pixbuf = greyed(pixbuf)
        return pixbuf
    return None


class ThemeIcons:
    """The icons of the rows of one kind: an icon of the theme, for all."""

    def __init__(self, names: Iterable[str], size: int) -> None:
        names = tuple(names)
        self._pixbufs = {
            running: theme_icon(names, size, grey=not running)
            for running in (True, False)
        }

    def get(self, item: object, running: bool) -> GdkPixbuf.Pixbuf | None:
        return self._pixbufs[bool(running)]


def types(event: Gdk.EventKey) -> bool:
    """Whether a key typed in the list goes to the search: a character."""

    modifiers = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK
    if event.state & modifiers:
        return False
    return chr(Gdk.keyval_to_unicode(event.keyval)).isprintable()


def log_failures(
    deferreds: list[defer.Deferred[Any]], message: str, logger: Logger
) -> defer.Deferred[None]:
    """Wait for deferreds, and log with message the ones that fail."""

    def done(results: list[tuple[bool, Any]]) -> None:
        for success, value in results:
            if not success:
                logger.failure(message, value)

    return defer.DeferredList(deferreds, consumeErrors=True).addCallback(done)


class Row(Gtk.ListBoxRow, Generic[T]):
    """An object, what it is and what it does, and what can be done to it."""

    # The prefix of the actions of the menu.
    GROUP = ""
    # The action of the menu that the Delete key does.
    DELETE = "delete"
    # Whether the object starts and stops, with a button of the row.
    STARTS = True

    def __init__(
        self,
        gui: VBGUI,
        item: T,
        icons: Pictures[T],
        sizes: Gtk.SizeGroup,
    ) -> None:
        super().__init__(visible=True)
        self.gui = gui
        self.item = item
        self.icons = icons
        self.actions = self.make_actions()
        self.insert_action_group(self.GROUP, self.actions)

        box = Gtk.Box(
            visible=True,
            spacing=12,
            margin_start=14,
            margin_end=8,
            margin_top=6,
            margin_bottom=6,
        )
        self.icon = Gtk.Image(visible=True, pixel_size=ICON_SIZE)
        box.pack_start(self.icon, False, False, 0)
        text = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
        )
        self.name = Gtk.Label(
            visible=True,
            xalign=0.0,
            ellipsize=Pango.EllipsizeMode.END,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD)
            ),
        )
        self.detail = Gtk.Label(
            visible=True, xalign=0.0, ellipsize=Pango.EllipsizeMode.END
        )
        self.detail.get_style_context().add_class("dim-label")
        text.pack_start(self.name, False, False, 0)
        text.pack_start(self.detail, False, False, 0)
        box.pack_start(text, True, True, 0)

        self.state = Gtk.Box(visible=True, spacing=7)
        self.dot = styled(
            Gtk.Box(valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER),
            "state-dot",
        )
        self.warning = styled(
            Gtk.Image.new_from_icon_name(
                "dialog-warning-symbolic", Gtk.IconSize.MENU
            ),
            "state-warning",
        )
        self.state_label = Gtk.Label(visible=True, xalign=0.0)
        for widget in (self.dot, self.warning, self.state_label):
            self.state.pack_start(widget, False, False, 0)
        sizes.add_widget(self.state)
        box.pack_start(self.state, False, False, 0)

        self.startstop = Gtk.Button(
            visible=True, relief=Gtk.ReliefStyle.NONE, valign=Gtk.Align.CENTER
        )
        self.menu_button = Gtk.Button(
            visible=True, relief=Gtk.ReliefStyle.NONE, valign=Gtk.Align.CENTER
        )
        self.popover: Gtk.Popover | None = None
        if self.STARTS:
            box.pack_start(self.startstop, False, False, 0)
        box.pack_start(self.menu_button, False, False, 0)
        self.add(box)

        self.startstop.connect("clicked", self.on_startstop_clicked)
        self.menu_button.connect("clicked", self.on_menu_clicked)
        self.update()

    # What each kind of row says

    def make_actions(self) -> MenuActions:
        """The group of actions of the menu of the object."""

        raise NotImplementedError

    def menu_model(self) -> Gio.MenuModel:
        """The menu of the object, made now: it depends on the others."""

        raise NotImplementedError

    def update(self, processes: bool = False) -> None:
        """
        Say again what the object is and does, with show_state().
        processes asks for the process of a running object in place of its
        summary.
        """

        raise NotImplementedError

    def on_startstop_clicked(self, button: Gtk.Button) -> None:
        raise NotImplementedError

    # What the rows share

    def show_state(
        self,
        detail: str,
        state: str,
        running: bool,
        warning: bool,
        tooltip: str | None,
        dot: str = "running",
    ) -> None:
        """
        Show detail under the name, and the state in words, with a dot of
        the colour dot while running, or a warning sign. A warning means that
        the object can't start. tooltip explains the state.
        """

        name = self.item.name
        self.name.set_text(name)
        self.detail.set_text(detail)
        self.detail.set_tooltip_text(detail)

        pixbuf = self.icons.get(self.item, running)
        if pixbuf is None:
            self.icon.set_from_icon_name("image-missing", Gtk.IconSize.DND)
        else:
            self.icon.set_from_pixbuf(pixbuf)
        self.icon.set_opacity(1.0 if running else STOPPED_OPACITY)

        self.dot.set_visible(not warning)
        self.warning.set_visible(warning)
        context = self.dot.get_style_context()
        for name_of_dot in DOTS:
            context.remove_class(name_of_dot)
        if running:
            context.add_class(dot)
        self.state_label.set_text(state)
        self.state.set_tooltip_text(tooltip)

        if running:
            icon, what = "media-playback-stop-symbolic", _("Stop {name}")
        else:
            icon, what = "media-playback-start-symbolic", _("Start {name}")
        icon_button(self.startstop, icon, what.format(name=name))
        self.startstop.set_sensitive(not warning)
        icon_button(
            self.menu_button,
            "view-more-symbolic",
            _("Menu of {name}").format(name=name),
        )
        self.actions.update()

    def open_menu(self) -> Gtk.Popover:
        """Show the menu of the object under its button."""

        # a popover shows no keys
        popover = self.popover = Gtk.Popover.new_from_model(
            self.menu_button, self.menu_model()
        )
        popover.connect("closed", self.on_menu_closed)
        popover.popup()
        return popover

    def on_menu_clicked(self, button: Gtk.Button) -> None:
        self.open_menu()

    def on_menu_closed(self, popover: Gtk.Popover) -> None:
        if popover is self.popover:
            self.popover = None
        # later: GTK still uses the popover after "closed", and a click on
        # an item runs its action after it; destroyed now, the popover is
        # freed under GTK, and the action lost
        GLib.idle_add(popover.destroy)


def _activate(row: Row[Any], name: str) -> None:
    """Do the action name of the menu of row, unless it is greyed."""

    if row.actions.get_action_enabled(name):
        row.actions.activate_action(name, None)


class RowList(Gtk.ListBox, Generic[T]):
    """The objects of a kind, a row each."""

    # When no row is left: without a search or the running switch, with a
    # search, with the switch, with both.
    NONE = NO_MATCH = NONE_RUNNING = NO_RUNNING_MATCH = ""

    def __init__(self, gui: VBGUI, factory: BrickFactory) -> None:
        super().__init__(
            visible=True,
            selection_mode=Gtk.SelectionMode.SINGLE,
            activate_on_single_click=False,
        )
        self.gui = gui
        self.factory = factory
        self.search = ""
        self.only_running = False
        self.icons = self.make_icons()
        self._sizes = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        self._rows: dict[T, Row[T]] = {}

        self.placeholder = Gtk.Label(
            visible=True,
            wrap=True,
            margin=24,
            justify=Gtk.Justification.CENTER,
        )
        self.placeholder.get_style_context().add_class("dim-label")
        self.set_placeholder(self.placeholder)
        self.set_filter_func(self._visible)
        for item in self.items():
            self._add(item)
        self._update_placeholder()
        added, removed, changed = self.signals()
        added.connect(self.on_added)
        removed.connect(self.on_removed)
        changed.connect(self.on_changed)

    # What each kind of list says

    def signals(self) -> tuple[Signal, Signal, Signal]:
        """The factory's signals: an object added, removed, changed."""

        raise NotImplementedError

    def items(self) -> list[T]:
        """The objects, in their order."""

        raise NotImplementedError

    def make_row(self, item: T) -> Row[T]:
        raise NotImplementedError

    def kind(self, item: T) -> str:
        """The kind of an object in words, which the search finds."""

        return ""

    def prepare(self, row: Row[T]) -> None:
        """Make ready a row, before the list takes it."""

    def make_icons(self) -> Pictures[T]:
        """The icons of the rows: what gives, for an object, its picture."""

        raise NotImplementedError

    def running(self, item: T) -> bool:
        """Whether item shows with the running ones: it runs, or is in use."""

        raise NotImplementedError

    # What the lists share

    def close(self) -> None:
        """Stop following the factory."""

        added, removed, changed = self.signals()
        added.disconnect(self.on_added)
        removed.disconnect(self.on_removed)
        changed.disconnect(self.on_changed)

    def row_of(self, item: T) -> Row[T] | None:
        return self._rows.get(item)

    def item_of(self, row: Gtk.ListBoxRow) -> T:
        """The object of a row of the list."""

        assert isinstance(row, Row), "the list has only rows of objects"
        item: T = row.item
        return item

    def selected(self) -> T | None:
        row = self.get_selected_row()
        return None if row is None else self.item_of(row)

    def set_search(self, text: str) -> None:
        """Keep the objects whose name or kind has text in it."""

        self.search = text
        self.invalidate_filter()
        self._update_placeholder()

    def set_only_running(self, only: bool) -> None:
        """Keep only the running objects, and show their process."""

        self.only_running = only
        self.update()

    def update(self) -> None:
        for row in self._rows.values():
            row.update(self.only_running)
        self.invalidate_filter()
        self._update_placeholder()

    def _add(self, item: T) -> None:
        row = self.make_row(item)
        self._rows[item] = row
        self.prepare(row)
        self.add(row)

    def _visible(self, row: Gtk.ListBoxRow) -> bool:
        item = self.item_of(row)
        if self.only_running and not self.running(item):
            return False
        text = self.search.strip().casefold()
        return (
            text in item.name.casefold() or text in self.kind(item).casefold()
        )

    def _update_placeholder(self) -> None:
        text = self.search.strip()
        if text and self.only_running:
            words = self.NO_RUNNING_MATCH
        elif text:
            words = self.NO_MATCH
        elif self.only_running:
            words = self.NONE_RUNNING
        else:
            words = self.NONE
        self.placeholder.set_text(words.format(text=text))

    # The factory

    def on_added(self, item: T) -> None:
        # the list filters a row it takes
        self._add(item)

    def on_removed(self, item: T) -> None:
        row = self._rows.pop(item, None)
        if row is not None:
            row.destroy()
        # the objects that used it may change, and not be told
        self.update()

    def on_changed(self, item: T) -> None:
        # every row: an object's name shows in the rows of others
        self.update()


class RowsTab(Tab, Gtk.Stack, Generic[T]):
    """The objects of a kind, and what can be done with them."""

    # The words of the tab.
    NEW = SEARCH = RUNNING = EMPTY_TITLE = EMPTY_WORDS = ""
    # The picture of a project without objects, a file of the data folder.
    EMPTY_ICON = ""
    # Whether the objects start and stop: then Start All and Stop All.
    STARTS = True

    def __init__(self, gui: VBGUI, factory: BrickFactory) -> None:
        super().__init__(visible=True)
        self.gui = gui
        self.factory = factory
        self._menu: Gtk.Menu | None = None
        # the object whose settings show, and their panel
        self.configuring: T | None = None
        self._controller: Panel | None = None
        self.settings: Gtk.Box | None = None
        # the object running, and the first error of the draft
        self.running_bar: Gtk.InfoBar | None = None
        self.running_words: Gtk.Label | None = None
        self.why: Gtk.Label | None = None
        self.main_page = Gtk.Box(
            visible=True, orientation=Gtk.Orientation.VERTICAL
        )
        self.add_named(self.main_page, "main")

        header = Gtk.Box(visible=True, spacing=GAP, margin=GAP)
        self.new_button = _icon_button(self.NEW, "list-add-symbolic")
        self.search = Gtk.SearchEntry(
            visible=True, placeholder_text=self.SEARCH, width_chars=24
        )
        self.all_button = Gtk.RadioButton(
            visible=True, label=_("All"), draw_indicator=False
        )
        self.running_button = Gtk.RadioButton(
            visible=True,
            label=self.RUNNING,
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
        all_items = Gtk.Box(visible=True)
        all_items.get_style_context().add_class("linked")
        all_items.pack_start(self.start_button, False, False, 0)
        all_items.pack_start(self.stop_button, False, False, 0)
        for widget in (self.new_button, self.search, filters):
            header.pack_start(widget, False, False, 0)
        if self.STARTS:
            header.pack_end(all_items, False, False, 0)
        header.pack_end(self.count, False, False, 0)
        self.main_page.pack_start(header, False, False, 0)
        self.main_page.pack_start(
            Gtk.Separator(
                visible=True, orientation=Gtk.Orientation.HORIZONTAL
            ),
            False,
            False,
            0,
        )

        self.list = self.make_list()
        scrolled = Gtk.ScrolledWindow(
            visible=True, hscrollbar_policy=Gtk.PolicyType.NEVER
        )
        scrolled.add(self.list)
        self.empty = self._empty_page()
        self.pages = Gtk.Stack(visible=True)
        self.pages.add_named(scrolled, "list")
        self.pages.add_named(self.empty, "empty")
        self.main_page.pack_start(self.pages, True, True, 0)

        self.new_button.connect("clicked", self.on_new_clicked)
        self.start_button.connect("clicked", self.on_start_clicked)
        self.stop_button.connect("clicked", self.on_stop_clicked)
        self.search.connect("search-changed", self.on_search_changed)
        self.search.connect("stop-search", self.on_stop_search)
        self.running_button.connect("toggled", self.on_running_toggled)
        self.list.connect("button-press-event", self.on_button_press)
        self.list.connect("key-press-event", self.on_list_key_press)
        self.list.connect("row-activated", self.on_row_activated)
        self.connect("key-press-event", self.on_key_press)
        added, removed, changed = self.signals()
        for signal in (added, removed, changed):
            signal.connect(self.on_changed)
        removed.connect(self.on_removed)
        self.update()

    def signals(self) -> tuple[Signal, Signal, Signal]:
        """The factory's signals: an object added, removed, changed."""

        raise NotImplementedError

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
        icon = self.empty_picture()
        if icon is not None:
            image.set_from_pixbuf(icon)
        image.set_opacity(EMPTY_ICON_OPACITY)
        title = Gtk.Label(
            visible=True,
            label=self.EMPTY_TITLE,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
                Pango.attr_scale_new(1.3),
            ),
        )
        words = Gtk.Label(
            visible=True,
            label=self.EMPTY_WORDS,
            wrap=True,
            max_width_chars=40,
            justify=Gtk.Justification.CENTER,
        )
        words.get_style_context().add_class("dim-label")
        for widget in (image, title, words):
            page.pack_start(widget, False, False, 0)
        return page

    # What each kind of tab does

    def empty_picture(self) -> GdkPixbuf.Pixbuf | None:
        """The picture of a project without objects, grey."""

        return empty_icon(self.EMPTY_ICON)

    def make_list(self) -> RowList[T]:
        raise NotImplementedError

    def items(self) -> list[T]:
        """The objects, in their order."""

        raise NotImplementedError

    def count_text(self, items: list[T]) -> str:
        """How many of items run, of how many."""

        raise NotImplementedError

    def can_start(self, item: T) -> bool:
        """Whether Start All starts item."""

        raise NotImplementedError

    def start_all(self) -> defer.Deferred[None] | None:
        raise NotImplementedError

    def stop_all(self) -> defer.Deferred[None] | None:
        raise NotImplementedError

    def new_item(self) -> None:
        """What New does."""

        raise NotImplementedError

    def popup(
        self, widget: Gtk.Widget, event: Gdk.EventButton | None, item: T
    ) -> Gtk.Menu:
        """Open the menu of item, with its keys."""

        raise NotImplementedError

    def panel_for(self, item: T) -> Panel | None:
        """The panel of the settings of item, on a new draft, or None."""

        raise NotImplementedError

    def settings_words(self, item: T) -> str:
        """What the line above the settings of item says under its name."""

        raise NotImplementedError

    # What the tabs share

    def update(self) -> None:
        """The row above the list, and the page, for the objects there are."""

        items = self.items()
        self.pages.set_visible_child_name("list" if items else "empty")
        self.count.set_text(self.count_text(items) if items else "")
        for widget in (self.search, self.all_button, self.running_button):
            widget.set_sensitive(bool(items))
        if self.STARTS:
            self.start_button.set_sensitive(any(map(self.can_start, items)))
            self.stop_button.set_sensitive(any(map(self.list.running, items)))

    def open_menu(self, event: Gdk.EventButton | None = None) -> None:
        """
        Open the menu of the selected object: at the pointer for a click,
        under its button for the Menu key.
        """

        item = self.list.selected()
        if item is None:
            return
        widget: Gtk.Widget
        if event is None:
            row = self.list.row_of(item)
            assert row is not None, "the selected object has its row"
            widget = row.menu_button
        else:
            widget = self.list
        # kept while it shows
        self._menu = self.popup(widget, event, item)

    # The settings of an object

    def configure(self, item: T) -> None:
        """
        Show the settings of item in place of the list. Those of another
        object close first, as with Cancel. An object without a panel, as a
        router, shows nothing.
        """

        controller = self.panel_for(item)
        if controller is None:
            return
        if self.configuring is not None:
            self.close_settings()
        self.configuring = item
        self._controller = controller
        self.settings = self._settings_page(item, controller)
        self.add_named(self.settings, "settings")
        self.set_visible_child(self.settings)

    def _settings_page(self, item: T, controller: Panel) -> Gtk.Box:
        page = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        head = Gtk.Box(visible=True, spacing=12, margin=GAP)
        image = Gtk.Image(visible=True, pixel_size=ICON_SIZE)
        pixbuf = self.list.icons.get(item, self.list.running(item))
        if pixbuf is not None:
            image.set_from_pixbuf(pixbuf)
        text = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(
            visible=True,
            xalign=0.0,
            label=item.name,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD)
            ),
        )
        kind = Gtk.Label(
            visible=True, xalign=0.0, label=self.settings_words(item)
        )
        kind.get_style_context().add_class("dim-label")
        text.pack_start(name, False, False, 0)
        text.pack_start(kind, False, False, 0)
        head.pack_start(image, False, False, 0)
        head.pack_start(text, True, True, 0)

        scrolled = Gtk.ScrolledWindow(visible=True)
        # with a margin around it
        holder = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            margin_start=GAP,
            margin_end=GAP,
            margin_top=GAP,
        )
        panel = controller.widget
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
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        self.ok_button.connect("clicked", self.on_ok_clicked)
        why = self.why = Gtk.Label(
            visible=False, xalign=1.0, ellipsize=Pango.EllipsizeMode.END
        )
        why.get_style_context().add_class("error")
        actions.pack_end(why, True, True, 0)
        running_bar = self.running_bar = Gtk.InfoBar(
            message_type=Gtk.MessageType.INFO
        )
        self.running_words = Gtk.Label(visible=True, xalign=0.0, wrap=True)
        running_bar.get_content_area().add(self.running_words)
        controller.connect_changed(self.on_panel_changed)
        self.on_panel_changed(controller)
        self.show_running(controller)

        for widget, expand in (
            (head, False),
            (running_bar, False),
            (Gtk.Separator(visible=True), False),
            (scrolled, True),
            (Gtk.Separator(visible=True), False),
            (actions, False),
        ):
            page.pack_start(widget, expand, expand, 0)
        page.connect("key-press-event", self.on_settings_key_press)
        return page

    def show_running(self, panel: Panel) -> None:
        """The info bar of the panel, while its object runs."""

        assert self.running_bar is not None, "the settings show"
        assert self.running_words is not None, "the settings show"
        running = panel.running()
        if running:
            self.running_words.set_text(panel.running_words())
        self.running_bar.set_visible(running)

    def on_panel_changed(self, panel: Panel) -> None:
        assert self.why is not None, "the settings show"
        errors = panel.draft.errors()
        self.ok_button.set_sensitive(not errors)
        if errors:
            error = errors[0]
            row = panel.rows.get(error.key)
            if row is None:
                text = error.text
            else:
                text = _("{setting}: {problem}").format(
                    setting=row.title.get_text(), problem=error.text
                )
            self.why.set_text(text)
        self.why.set_visible(bool(errors))

    def on_ok_clicked(self, button: Gtk.Button) -> None:
        panel = self._controller
        assert panel is not None, "OK is of the settings that show"
        panel.commit()
        # a number just taken can make an error, which shows beside OK
        if panel.draft.errors():
            return
        applying = self.gui.engine.apply(panel.draft)
        applying.addCallbacks(
            lambda _: self.close_settings(), self._not_applied
        )

    def _not_applied(self, failure: Failure) -> None:
        """The engine refused the draft: why shows beside OK."""

        if self.why is None:
            # the settings closed meanwhile
            return
        self.why.set_text(failure.getErrorMessage())
        self.why.set_visible(True)

    def on_cancel_clicked(self, button: Gtk.Button) -> None:
        self.close_settings()

    def close_settings(self) -> None:
        """Back to the list, on the object configured."""

        item = self.configuring
        if item is None:
            return
        self.configuring = self._controller = None
        self.running_bar = self.running_words = self.why = None
        # the stack shows the list once the page goes
        assert self.settings is not None, "the settings of item show"
        self.settings.destroy()
        self.settings = None
        row = self.list.row_of(item)
        if row is not None:
            self.list.select_row(row)
            row.grab_focus()

    # What the main window tells

    def on_open(self) -> None:
        if self.configuring is not None:
            self.close_settings()
        # an entry emptied tells the list at once
        self.search.set_text("")
        self.all_button.set_active(True)

    def on_quit(self) -> None:
        self.list.close()
        added, removed, changed = self.signals()
        for signal in (added, removed, changed):
            signal.disconnect(self.on_changed)
        removed.disconnect(self.on_removed)

    # Signals

    def on_changed(self, item: T) -> None:
        self.update()
        if item is self.configuring:
            assert self._controller is not None, "item's settings show"
            self.show_running(self._controller)

    def on_removed(self, item: T) -> None:
        if item is self.configuring:
            self.close_settings()

    def on_settings_key_press(
        self, page: Gtk.Box, event: Gdk.EventKey
    ) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.close_settings()
            return True
        return False

    def on_new_clicked(self, button: Gtk.Button) -> None:
        self.new_item()

    def on_start_clicked(self, button: Gtk.Button) -> None:
        self.start_all()

    def on_stop_clicked(self, button: Gtk.Button) -> None:
        self.stop_all()

    def on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self.list.set_search(entry.get_text())

    def on_stop_search(self, entry: Gtk.SearchEntry) -> None:
        entry.set_text("")
        # back to the list, on the selected object or the first
        row = self.list.get_selected_row() or self.list.get_row_at_index(0)
        if row is not None:
            row.grab_focus()

    def on_running_toggled(self, button: Gtk.RadioButton) -> None:
        self.list.set_only_running(button.get_active())

    def on_row_activated(
        self, listbox: RowList[T], row: Gtk.ListBoxRow
    ) -> None:
        self.gui.curtain_up(listbox.item_of(row))

    def on_button_press(
        self, listbox: RowList[T], event: Gdk.EventButton
    ) -> bool:
        if not event.triggers_context_menu():
            return False
        row = listbox.get_row_at_y(int(event.y))
        if row is None:
            return False
        listbox.select_row(row)
        row.grab_focus()
        self.open_menu(event)
        return True

    def on_list_key_press(
        self, listbox: RowList[T], event: Gdk.EventKey
    ) -> bool:
        keyval = event.keyval
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        item = listbox.selected()
        if keyval == Gdk.KEY_Menu or (keyval == Gdk.KEY_F10 and shift):
            self.open_menu()
            return True
        row = None if item is None else listbox.row_of(item)
        if row is not None and keyval in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete):
            _activate(row, row.DELETE)
            return True
        if row is not None and keyval == Gdk.KEY_F2:
            _activate(row, "rename")
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

    def on_key_press(self, tab: RowsTab[T], event: Gdk.EventKey) -> bool:
        control = event.state & Gdk.ModifierType.CONTROL_MASK
        if self.configuring is not None:
            return False
        if control and event.keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search.grab_focus()
            return True
        return False
