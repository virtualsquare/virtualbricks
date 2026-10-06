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
The Settings window (page 23): a page for each owner of settings, each a
form on a draft, and Cancel and OK in the header bar.

On the machine of the bricks, two pages: This computer, the settings of its
settings.toml, in two sections, those of these windows and those of the
bricks; and the open project's. Over a connection, three (page 19 R10): the
section of the bricks is the page of the machine there, which keeps them,
and the folders of the project are paths there, typed, with the folders
there to complete them.

The facts that the drafts check against come from the engine when the
window opens, and again half a second after the last key typed in a folder
of the programs. A page with an error marks its tab, and OK, greyed out,
says the first in its tooltip.

OK writes what changed, and nothing else: the settings of this computer
here, those of the machine of the bricks and of the project through the
engine. If KSM changed, the window waits for it to turn: when it doesn't,
the window stays open on its page, whose row says so, and OK tries again.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, cast

import attr
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from twisted.internet import defer  # noqa: E402
from twisted.internet.interfaces import (  # noqa: E402
    IDelayedCall,
    IReactorTime,
)
from twisted.logger import Logger  # noqa: E402
from twisted.python.failure import Failure  # noqa: E402

from virtualbricks import ksm, locations  # noqa: E402
from virtualbricks.config import settings  # noqa: E402
from virtualbricks.config.settings import (  # noqa: E402
    AppSettings,
    ProjectSettings,
    SettingValue,
    get_setting,
    set_setting,
    store_settings,
)
from virtualbricks.engine import Engine  # noqa: E402
from virtualbricks.gui.dialogs.base import Window  # noqa: E402
from virtualbricks.gui.form import (  # noqa: E402
    Form,
    set_options,
)
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.locations import short_path  # noqa: E402
from virtualbricks.programs import FolderPrograms, QemuInfo  # noqa: E402
from virtualbricks.settingsdraft import (  # noqa: E402
    PLAYING,
    Facts,
    Owner,
    SettingsDraft,
    audio_drivers,
    terminals,
)

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.gui.mainwindow.window import VBGUI
    from virtualbricks.remote.mirror import MirrorFactory

logger = Logger()
settings_not_saved = "The settings weren't saved: {error}"

# The settings of these windows, and those of the bricks, which the machine
# of the bricks keeps.
WINDOWS = ("terminal", "tray_icon", "warn_missing_programs")
BRICKS = ("kernel_samepage_merging", "audio_driver", "workspace")
# Those of the project.
PROGRAMS = ("qemu_path", "vde_path")
LINKS = ("allow_female_plugs", "log_link_loops")
KSM = "kernel_samepage_merging"
# Seconds after the last key in a folder before the window asks what it holds.
FOLDER_DELAY = 0.5
WIDTH = 640
MARGIN = 12


def _write_here(changes: dict[str, SettingValue]) -> defer.Deferred[None]:
    """Write settings of this computer, in its settings.toml."""

    for name, value in changes.items():
        set_setting(name, value)
    store_settings()
    return defer.succeed(None)


class Page:
    """A page of the window: its draft, its form, and the mark of its tab."""

    def __init__(
        self,
        title: str,
        draft: SettingsDraft,
        engine: Engine,
        changed: Callable[[Page], None],
    ) -> None:
        self.title = title
        self.draft = draft
        self.form = Form(draft, lambda: changed(self), engine)
        self.mark = Gtk.Image.new_from_icon_name(
            "dialog-error-symbolic", Gtk.IconSize.MENU
        )
        self.tab = Gtk.Box(visible=True, spacing=4)
        self.tab.pack_start(
            Gtk.Label(visible=True, label=title), False, False, 0
        )
        self.tab.pack_start(self.mark, False, False, 0)

    def label_of(self, key: str) -> str:
        row = self.form.rows.get(key)
        return key if row is None else row.title.get_text()


class SettingsWindow(Window):
    """The settings of these windows, of the machine of the bricks, and of
    the open project."""

    def __init__(self, gui: VBGUI, clock: IReactorTime | None = None) -> None:
        if clock is None:
            from twisted.internet import reactor

            clock = cast("IReactorTime", reactor)
        self.gui = gui
        self.engine = gui.engine
        self.clock = clock
        available: bool | None
        if self.engine.local:
            available = ksm.ksm_available()
            where = ""
        else:
            available = self.engine.factory.machine.get("ksm_available")
            where = self.engine.where
        self.facts = Facts(ksm_available=available, where=where)
        self.pages: list[Page] = []
        # the facts asked last, of which folders, and the call that asks
        # them again
        self._asking = 0
        self._asked: tuple[str, str] | None = None
        self._later: IDelayedCall | None = None
        # while OK waits for KSM; once the window is gone
        self._turning = False
        self._closed = False
        super().__init__()
        self._follow()
        self.ask_facts()

    # The window

    def build_ui(self) -> None:
        self.dialog = Gtk.Dialog(
            title=_("Settings"),
            use_header_bar=True,
            modal=True,
            destroy_with_parent=True,
        )
        self.dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.ok_button = self.dialog.add_button(_("OK"), Gtk.ResponseType.OK)
        self.ok_button.get_style_context().add_class("suggested-action")
        self.spinner = Gtk.Spinner()
        self.dialog.get_header_bar().pack_end(self.spinner)
        self.notebook = Gtk.Notebook(visible=True)
        # as wide as this at least: a window is as tall as its content is at
        # its narrowest, where the captions take more lines
        self.notebook.set_size_request(WIDTH, -1)
        # and as wide as this when it opens: else GTK opens a window as wide
        # as its content wants, up to the screen, and a caption that wraps
        # wants all of its text on one line
        self.dialog.set_default_size(WIDTH, -1)
        self.dialog.get_content_area().pack_start(self.notebook, True, True, 0)
        engine = self.engine
        here = Owner(AppSettings, get_setting, engine.set_settings)
        if engine.local:
            computer = self._page(
                _("This computer"),
                SettingsDraft(here, WINDOWS + BRICKS),
                _("Kept in {path}").format(
                    path=short_path(locations.settings_file())
                ),
            )
            self._windows(computer.form)
            self._bricks(computer.form)
        else:
            here.write = _write_here
            computer = self._page(
                _("This computer"),
                SettingsDraft(here, WINDOWS),
                _("Kept in {path}").format(
                    path=short_path(locations.settings_file())
                ),
            )
            self._windows(computer.form)
            there = Owner(
                AppSettings, engine.machine.setting, engine.set_settings
            )
            machine = self._page(
                engine.where,
                SettingsDraft(there, BRICKS),
                _("Kept on {where}, in its settings.toml").format(
                    where=engine.where
                ),
            )
            self._bricks(machine.form)
        self.project_page = self._project_page()
        self.dialog.connect("response", self.on_response)
        self.dialog.connect("destroy", self.on_destroy)
        self.refresh()

    def _page(self, title: str, draft: SettingsDraft, where: str) -> Page:
        """A page, under a line that says where its settings are kept."""

        page = Page(title, draft, self.engine, self.on_changed)
        box = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin=MARGIN,
        )
        line = Gtk.Label(visible=True, xalign=0.0, wrap=True, label=where)
        line.get_style_context().add_class("dim-label")
        box.pack_start(line, False, False, 0)
        box.pack_start(page.form.widget, False, False, 0)
        self.notebook.append_page(box, page.tab)
        self.pages.append(page)
        return page

    def _windows(self, form: Form) -> None:
        form.section(_("Windows"))
        form.combo_entry("terminal", terminals(self.facts.which))
        form.switch("tray_icon")
        form.switch("warn_missing_programs")

    def _bricks(self, form: Form) -> None:
        form.section(_("Bricks"))
        form.switch(KSM)
        self.audio_combo = form.combo_entry("audio_driver", PLAYING)
        if self.engine.local:
            form.value("workspace", short_path)
        else:
            form.value("workspace")

    def _project_page(self) -> Page:
        engine = self.engine
        current = engine.workspace.current
        owner = Owner(
            ProjectSettings, engine.machine.setting, engine.set_settings
        )
        if current is None:
            title = _("Project")
            where = _(
                "No project is open. A new project starts with these"
                " settings, the defaults; open one to change its own."
            )
        else:
            title = _("Project {name}").format(name=current.name)
            assert current.path is not None, "the project there has a folder"
            path = os.path.join(current.path, locations.PROJECT_FILE)
            if engine.local:
                where = _(
                    "Kept in {path}. A new project starts with a copy of them."
                ).format(path=short_path(path))
            else:
                where = _(
                    "Kept in {path} on {where}. A new project starts with a"
                    " copy of them."
                ).format(path=path, where=engine.where)
        page = self._page(title, SettingsDraft(owner, PROGRAMS + LINKS), where)
        form = page.form
        form.section(_("Programs"))
        form.path("qemu_path", _("The Folder of the QEMU Programs"), True)
        form.path("vde_path", _("The Folder of the VDE Programs"), True)
        form.section(_("Links"))
        form.switch("allow_female_plugs")
        form.switch("log_link_loops")
        # its defaults, which can't be changed while no project is open
        form.widget.set_sensitive(current is not None)
        return page

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def refresh(self) -> None:
        """
        The rows as the drafts say, the marks of the tabs, and OK: greyed
        out while a page has an error, which its tooltip says.
        """

        first = None
        for page in self.pages:
            page.form.refresh()
            errors = page.draft.errors()
            page.mark.set_visible(bool(errors))
            if errors and first is None:
                first = (page, errors[0])
        self.ok_button.set_sensitive(first is None and not self._turning)
        if first is None:
            self.ok_button.set_tooltip_text(None)
        else:
            page, problem = first
            self.ok_button.set_tooltip_text(
                _("{page}: {setting}: {problem}").format(
                    page=page.title,
                    setting=page.label_of(problem.key),
                    problem=problem.text,
                )
            )

    def on_changed(self, page: Page) -> None:
        self.refresh()
        if page is self.project_page and self._folders() != self._asked:
            self._ask_later()

    def _folders(self) -> tuple[str, str]:
        draft = self.project_page.draft
        return draft.get("vde_path"), draft.get("qemu_path")

    # The facts

    def _ask_later(self) -> None:
        if self._later is not None and self._later.active():
            self._later.cancel()
        self._later = self.clock.callLater(FOLDER_DELAY, self.ask_facts)

    def set_facts(self, **facts: Any) -> None:
        """New facts, for every draft: the rows say them."""

        self.facts = attr.evolve(self.facts, **facts)
        for page in self.pages:
            page.draft.facts = self.facts
        self.refresh()

    def ask_facts(self) -> defer.Deferred[Any]:
        """
        What the folders of the project's page hold, then what the QEMU of
        the folder lists; the answers of an older question are dropped.
        """

        self._asking += 1
        asking = self._asking
        self._asked = self._folders()
        question = self.engine.programs_found(*self._asked)

        def found(
            answer: tuple[FolderPrograms, FolderPrograms],
        ) -> defer.Deferred[None]:
            if asking != self._asking:
                return defer.succeed(None)
            vde, qemu = answer
            self.set_facts(
                vde=vde, qemu=qemu, qemu_version="", audio_drivers=None
            )
            path = qemu.qemu()
            if path is None:
                return defer.succeed(None)
            return self.engine.qemu(path).addCallback(listed)

        def listed(info: QemuInfo) -> None:
            if asking != self._asking:
                return
            self.set_facts(
                qemu_version=str(info.version),
                audio_drivers=info.audio_drivers,
            )
            if info.audio_drivers is not None:
                playing, others = audio_drivers(info.audio_drivers)
                set_options(
                    self.audio_combo,
                    playing + ([""] if playing and others else []) + others,
                )

        def failed(failure: Failure) -> None:
            # no facts: the rows say nothing more
            logger.debug(
                "Facts for the Settings window: {error}",
                error=failure.getErrorMessage(),
            )

        return question.addCallback(found).addErrback(failed)

    # What changes elsewhere

    def _follow(self) -> None:
        settings.changed.connect(self.on_setting_changed)
        if not self.engine.local:
            self.engine.factory.settings_changed.connect(
                self.on_settings_there
            )

    def _unfollow(self) -> None:
        settings.changed.disconnect(self.on_setting_changed)
        if not self.engine.local:
            self.engine.factory.settings_changed.disconnect(
                self.on_settings_there
            )

    def _take(self, pages: Iterable[Page], name: str, value: object) -> None:
        for page in pages:
            if name in page.draft.keys and page.draft.follow(name, value):
                page.form.reload()

    def on_setting_changed(self, name: str) -> None:
        """A setting of this process changed, as in its console."""

        if self.engine.local:
            pages = self.pages
        else:
            # the settings of this computer
            pages = self.pages[:1]
        self._take(pages, name, get_setting(name))
        self.refresh()

    def on_settings_there(self, copy: MirrorFactory) -> None:
        """The settings of the Virtualbricks there changed."""

        for name, value in copy.settings.items():
            self._take(self.pages[1:], name, value)
        self.refresh()

    # Cancel and OK

    def on_response(self, dialog: Gtk.Dialog, response_id: int) -> bool:
        if response_id == Gtk.ResponseType.OK:
            self.ok()
        else:
            dialog.destroy()
        return True

    def on_destroy(self, dialog: Gtk.Dialog) -> None:
        self._closed = True
        self._unfollow()
        if self._later is not None and self._later.active():
            self._later.cancel()

    def _ksm_page(self) -> Page | None:
        for page in self.pages:
            if KSM in page.draft.keys:
                return page
        return None

    def ok(self) -> defer.Deferred[bool]:
        """
        Write what changed; then, if KSM changed, or didn't turn the last
        time, wait for it. The window closes when all went as asked.
        """

        # the changes to write, by what writes them
        writes: dict[Callable[[dict[str, Any]], object], dict[str, Any]]
        writes = {}
        for page in self.pages:
            changes = page.draft.changes()
            if changes:
                writes.setdefault(page.draft.brick.write, {}).update(changes)
        tray = None
        for changes in writes.values():
            tray = changes.get("tray_icon", tray)
        ksm_page = self._ksm_page()
        turn = ksm_page is not None and (
            KSM in ksm_page.draft.changes() or KSM in ksm_page.draft.failed
        )
        self._turning = True
        self.refresh()
        writing = defer.gatherResults(
            [
                defer.maybeDeferred(write, changes)
                for write, changes in writes.items()
            ],
            consumeErrors=True,
        )

        def written(_: object) -> bool | defer.Deferred[bool]:
            for page in self.pages:
                page.draft.saved()
            if tray is not None:
                if tray:
                    self.gui.start_systray()
                else:
                    self.gui.stop_systray()
            if not turn or ksm_page is None:
                return True
            wanted = ksm_page.draft.get(KSM)
            self.spinner.start()
            self.spinner.show()
            turning = self.engine.set_ksm(wanted)
            return turning.addCallback(
                lambda state: self._turned(wanted, state)
            )

        def not_written(failure: Failure) -> bool:
            first = failure.value
            assert isinstance(first, defer.FirstError), "gatherResults failed"
            error = first.subFailure.getErrorMessage()
            logger.error(settings_not_saved, error=error)
            return False

        def done(close: bool) -> bool:
            self._turning = False
            self.spinner.stop()
            self.spinner.hide()
            if self._closed:
                # Cancel, while KSM turned
                return close
            if close:
                self.dialog.destroy()
            else:
                self.refresh()
            return close

        return writing.addCallbacks(written, not_written).addCallback(done)

    def _turned(self, wanted: bool, state: bool) -> bool:
        """Whether KSM turned as asked; if not, its row says so."""

        if state == wanted:
            return True
        page = self._ksm_page()
        assert page is not None, "a window that turns KSM has its page"
        if wanted:
            text = _(
                "KSM is still off: Virtualbricks couldn't turn it on. File ›"
                " Logs says why."
            )
        else:
            text = _(
                "KSM is still on: Virtualbricks couldn't turn it off. File ›"
                " Logs says why."
            )
        page.draft.fail(KSM, text)
        self.notebook.set_current_page(self.pages.index(page))
        return False
