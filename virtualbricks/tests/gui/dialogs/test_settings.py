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


"""The Settings window: its pages, its rows, Cancel and OK (page 23)."""

import os
from types import SimpleNamespace

from twisted.internet import defer, task

from virtualbricks import ksm, locations
from virtualbricks.config.settings import get_setting, set_setting
from virtualbricks.config.tomlfile import load_toml
from virtualbricks.observable import Observable, Signal
from virtualbricks.programs import REQUIRED, FolderPrograms, Missing, Version
from virtualbricks.tests.gui import (
    FakeGui,
    GuiTestCase,
    has_display,
    untranslated,
)

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui.dialogs import settings as settings_window

DRIVERS = frozenset({"alsa", "none", "pa", "pipewire", "wav"})


def vde(folder, missing=(), exists=True):
    return FolderPrograms(
        folder,
        exists,
        {name: f"{folder}/{name}" for name in REQUIRED if name not in missing},
        tuple(Missing(name, "vde2") for name in missing),
    )


def qemu(folder, exists=True):
    found = {
        name: f"{folder}/{name}"
        for name in ("qemu-img", "qemu-system-i386", "qemu-system-x86_64")
    }
    return FolderPrograms(folder, exists, found, ())


class Facts:
    """What the engine says of the folders and of QEMU, and the questions."""

    def __init__(self, missing=(), exists=True):
        self.missing = missing
        self.exists = exists
        self.asked = []
        self.probed = []
        # the answers held back, if any
        self.held = None

    def programs_found(self, vde_path, qemu_path):
        self.asked.append((vde_path, qemu_path))
        answer = (
            vde(vde_path, self.missing),
            qemu(qemu_path, self.exists),
        )
        if self.held is not None:
            held = defer.Deferred()
            self.held.append((held, answer))
            return held
        return defer.succeed(answer)

    def qemu(self, path):
        self.probed.append(path)
        return defer.succeed(
            SimpleNamespace(version=Version(10, 0, 11), audio_drivers=DRIVERS)
        )


def row(window, name):
    for page in window.pages:
        if name in page.form.rows:
            return page.form.rows[name]
    raise KeyError(name)


def control(window, name):
    """The widget of a setting: the entry of a text, as the label says."""

    return row(window, name).title.get_mnemonic_widget()


class WindowTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.clock = task.Clock()
        self.facts = Facts()
        self.available = True
        self.patch(ksm, "ksm_available", lambda: self.available)
        self.closed = []

    def gui(self):
        gui = FakeGui(self.factory)
        gui.engine.programs_found = self.facts.programs_found
        gui.engine.qemu = self.facts.qemu
        return gui

    def window(self, gui=None):
        window = settings_window.SettingsWindow(gui or self.gui(), self.clock)
        window.dialog.connect("destroy", lambda _: self.closed.append(True))
        self.addCleanup(window.dialog.destroy)
        return window

    def open_project(self, name="lab"):
        self.manager.create(name)
        self.manager.open(name, self.factory)
        return self.manager.current

    def ok(self, window):
        return self.successResultOf(window.ok())


class TestPages(WindowTestCase):

    def test_with_a_project(self):
        self.open_project()
        window = self.window()
        self.assertEqual(
            [page.title for page in window.pages],
            ["This computer", "Project lab"],
        )
        self.assertEqual(window.notebook.get_n_pages(), 2)
        computer, project = window.pages
        self.assertEqual(
            computer.draft.keys,
            settings_window.WINDOWS + settings_window.BRICKS,
        )
        self.assertTrue(project.form.widget.get_sensitive())

    def test_its_width(self):
        # not as wide as the captions on one line, as GTK would open it
        window = self.window()
        width, height = window.dialog.get_default_size()
        self.assertEqual((width, height), (settings_window.WIDTH, -1))
        # nor narrower
        self.assertEqual(
            window.notebook.get_size_request(), (settings_window.WIDTH, -1)
        )

    def test_without_a_project(self):
        window = self.window()
        project = window.pages[-1]
        self.assertEqual(project.title, "Project")
        # the defaults, which can't be changed
        self.assertFalse(project.form.widget.get_sensitive())
        self.assertEqual(control(window, "qemu_path").get_text(), "/usr/bin")

    def test_rows_from_the_schema(self):
        window = self.window()
        terminal = row(window, "terminal")
        self.assertEqual(terminal.title.get_text(), "Terminal")
        self.assertEqual(
            terminal.help, "The terminal that opens the consoles of the bricks"
        )
        self.assertEqual(
            row(window, "allow_female_plugs").title.get_text(),
            "Plugs into machines",
        )
        # the workspace, shown and not changed
        self.assertIsInstance(control(window, "workspace"), Gtk.Label)
        self.assertEqual(
            control(window, "workspace").get_text(),
            locations.short_path(get_setting("workspace")),
        )

    def test_the_terminals_found(self):
        window = self.window()
        combo = row(window, "terminal").control
        model = combo.get_model()
        found = [model[index][0] for index in range(len(model))]
        self.assertEqual(found, settings_window.terminals())


class TestOk(WindowTestCase):

    def setUp(self):
        super().setUp()
        self.project = self.open_project()

    def test_only_what_changed(self):
        window = self.window()
        control(window, "terminal").set_text("/usr/bin/foot")
        control(window, "log_link_loops").set_active(True)
        # meanwhile, the console
        set_setting("warn_missing_programs", False)
        self.assertTrue(self.ok(window))
        self.assertEqual(get_setting("terminal"), "/usr/bin/foot")
        self.assertIs(self.project.settings.log_link_loops, True)
        # the console's stays
        self.assertIs(get_setting("warn_missing_programs"), False)
        data = load_toml(locations.settings_file())
        self.assertEqual(data["terminal"], "/usr/bin/foot")
        self.assertNotIn("log_link_loops", data)
        project = load_toml(self.project.project_file)
        self.assertIs(project["settings"]["log_link_loops"], True)
        self.assertEqual(self.closed, [True])
        # nothing about the tray or KSM
        self.assertEqual(window.gui.systray, [])
        self.assertEqual(self.ksm, [])

    def test_follows_the_console(self):
        window = self.window()
        set_setting("terminal", "xterm")
        self.assertEqual(control(window, "terminal").get_text(), "xterm")
        # a setting changed in the window keeps the window's value
        control(window, "qemu_path").set_text("/opt/qemu")
        set_setting("qemu_path", "/srv/qemu")
        self.assertEqual(control(window, "qemu_path").get_text(), "/opt/qemu")
        self.ok(window)
        self.assertEqual(get_setting("qemu_path"), "/opt/qemu")

    def test_cancel(self):
        window = self.window()
        control(window, "terminal").set_text("/usr/bin/foot")
        control(window, "kernel_samepage_merging").set_active(True)
        window.on_response(window.dialog, Gtk.ResponseType.CANCEL)
        self.assertEqual(self.closed, [True])
        self.assertEqual(get_setting("terminal"), "x-terminal-emulator")
        self.assertFalse(os.path.exists(locations.settings_file()))
        self.assertEqual(self.ksm, [])

    def test_tray_icon(self):
        window = self.window()
        control(window, "tray_icon").set_active(False)
        self.ok(window)
        self.assertEqual(window.gui.systray, ["stop"])

    def test_a_failure(self):
        window = self.window()

        def refuse(values):
            return defer.fail(OSError("disk full"))

        window.engine.set_settings = refuse
        for page in window.pages:
            page.draft.brick.write = refuse
        self.patch(settings_window, "logger", FakeLoggerHere())
        control(window, "terminal").set_text("/usr/bin/foot")
        self.assertFalse(self.ok(window))
        # open, and OK again
        self.assertEqual(self.closed, [])
        self.assertTrue(window.ok_button.get_sensitive())


class FakeLoggerHere:
    def __init__(self):
        self.errors = []

    def error(self, text, **kwargs):
        self.errors.append(text.format(**kwargs))

    def debug(self, text, **kwargs):
        pass


class TestKsm(WindowTestCase):

    def test_turned_on(self):
        window = self.window()
        control(window, "kernel_samepage_merging").set_active(True)
        self.assertTrue(self.ok(window))
        self.assertEqual(self.ksm, [True])
        self.assertIs(get_setting("kernel_samepage_merging"), True)
        self.assertEqual(self.closed, [True])

    def test_waits(self):
        turning = defer.Deferred()
        self.patch(ksm, "set_ksm", lambda enable: turning)
        window = self.window()
        control(window, "kernel_samepage_merging").set_active(True)
        ok = window.ok()
        self.assertNoResult(ok)
        self.assertFalse(window.ok_button.get_sensitive())
        turning.callback(True)
        self.assertTrue(self.successResultOf(ok))

    def test_refused(self):
        self.patch(ksm, "set_ksm", lambda enable: defer.succeed(False))
        window = self.window()
        window.notebook.set_current_page(1)
        control(window, "kernel_samepage_merging").set_active(True)
        self.assertFalse(self.ok(window))
        # open, on the page of KSM, which says why
        self.assertEqual(self.closed, [])
        self.assertEqual(window.notebook.get_current_page(), 0)
        problem = row(window, "kernel_samepage_merging").problem
        self.assertTrue(problem.get_visible())
        self.assertEqual(
            problem.get_text(),
            "KSM is still off: Virtualbricks couldn't turn it on. File ›"
            " Logs says why.",
        )
        # a warning: OK tries again
        self.assertTrue(window.ok_button.get_sensitive())
        self.patch(ksm, "set_ksm", lambda enable: defer.succeed(enable))
        self.assertTrue(self.ok(window))
        self.assertEqual(self.closed, [True])

    def test_not_changed(self):
        window = self.window()
        self.ok(window)
        self.assertEqual(self.ksm, [])

    def test_no_ksm_here(self):
        self.available = False
        window = self.window()
        self.assertFalse(
            row(window, "kernel_samepage_merging").get_sensitive()
        )
        self.assertIn(
            "This Linux has no KSM",
            row(window, "kernel_samepage_merging").caption.get_text(),
        )

    def test_cancel_while_it_turns(self):
        turning = defer.Deferred()
        self.patch(ksm, "set_ksm", lambda enable: turning)
        window = self.window()
        control(window, "kernel_samepage_merging").set_active(True)
        ok = window.ok()
        window.on_response(window.dialog, Gtk.ResponseType.CANCEL)
        turning.callback(True)
        self.successResultOf(ok)
        self.assertEqual(self.closed, [True])


class TestFacts(WindowTestCase):

    def setUp(self):
        super().setUp()
        self.open_project()

    def test_at_once(self):
        self.facts.missing = ("vde_cryptcab",)
        window = self.window()
        self.assertEqual(self.facts.asked, [("/usr/bin", "/usr/bin")])
        self.assertEqual(self.facts.probed, ["/usr/bin/qemu-system-x86_64"])
        self.assertIn(
            "QEMU 10.0.11: qemu-img and qemu-system-i386 and x86_64",
            row(window, "qemu_path").caption.get_text(),
        )
        vde_row = row(window, "vde_path")
        self.assertEqual(
            vde_row.problem.get_text(),
            "Missing here and in PATH: vde_cryptcab (vde2)",
        )
        # only a warning
        self.assertTrue(window.ok_button.get_sensitive())

    def test_audio_drivers(self):
        window = self.window()
        model = window.audio_combo.get_model()
        self.assertEqual(
            [model[index][0] for index in range(len(model))],
            ["pipewire", "pa", "alsa", "", "none", "wav"],
        )
        control(window, "audio_driver").set_text("sndio")
        self.assertEqual(
            row(window, "audio_driver").problem.get_text(),
            "QEMU 10.0.11 has no audio driver sndio: a machine with a sound"
            " card starts without it",
        )

    def test_a_folder_typed(self):
        window = self.window()
        entry = control(window, "qemu_path")
        entry.set_text("/opt/q")
        entry.set_text("/opt/qemu")
        # after the last key
        self.clock.advance(settings_window.FOLDER_DELAY - 0.1)
        self.assertEqual(len(self.facts.asked), 1)
        self.clock.advance(0.1)
        self.assertEqual(self.facts.asked[-1], ("/usr/bin", "/opt/qemu"))
        self.assertEqual(len(self.facts.asked), 2)

    def test_a_switch_asks_nothing(self):
        window = self.window()
        control(window, "log_link_loops").set_active(True)
        self.clock.advance(1)
        self.assertEqual(len(self.facts.asked), 1)

    def test_no_folder(self):
        window = self.window()
        self.facts.exists = False
        control(window, "qemu_path").set_text("/opt/qemu")
        self.clock.advance(settings_window.FOLDER_DELAY)
        project = window.pages[-1]
        self.assertTrue(project.mark.get_visible())
        self.assertFalse(window.ok_button.get_sensitive())
        self.assertEqual(
            window.ok_button.get_tooltip_text(),
            "Project lab: QEMU folder: No folder /opt/qemu",
        )

    def test_an_older_answer(self):
        self.facts.held = []
        window = self.window()
        control(window, "qemu_path").set_text("/opt/qemu")
        self.clock.advance(settings_window.FOLDER_DELAY)
        [(first, answer1), (second, answer2)] = self.facts.held
        second.callback(answer2)
        # the answer of the first question comes last: dropped
        first.callback(answer1)
        self.assertEqual(window.facts.qemu.folder, "/opt/qemu")


class Copy:
    """The copy of the project there, as the window reads it."""

    def __init__(self, values):
        self.settings = values
        self.machine = {"ksm_available": True}
        self.settings_changed = Signal(Observable(), "settings-changed")


class SettingsThere:
    def __init__(self, copy):
        self.copy = copy

    def setting(self, name):
        return self.copy.settings[name]


class OpenThere:
    name = "ospf"
    path = "/srv/labs/ospf"


class WorkspaceThere:
    path = "/srv/labs"
    current = OpenThere()


class EngineThere:
    """The engine of windows over a connection: what it sends there."""

    local = False
    where = "lab.example"

    def __init__(self, values, facts):
        self.factory = Copy(values)
        self.machine = SettingsThere(self.factory)
        self.workspace = WorkspaceThere()
        self.programs_found = facts.programs_found
        self.qemu = facts.qemu
        self.sent = []

    def set_settings(self, values):
        self.sent.append(("settings", values))
        return defer.succeed(None)

    def set_ksm(self, enable):
        self.sent.append(("ksm", enable))
        return defer.succeed(enable)


class TestOverAConnection(WindowTestCase):
    """This computer, the machine there, the project there (19 R10)."""

    def setUp(self):
        super().setUp()
        values = {
            name: get_setting(name)
            for name in ("workspace", "terminal", "tray_icon")
            + ("warn_missing_programs",)
        }
        values.update(
            {
                "workspace": "/srv/labs",
                "kernel_samepage_merging": True,
                "audio_driver": "pipewire",
                "vde_path": "/opt/vde/bin",
                "qemu_path": "/opt/qemu/bin",
                "allow_female_plugs": True,
                "log_link_loops": False,
            }
        )
        self.engine = EngineThere(values, self.facts)
        gui = FakeGui(self.factory)
        gui.engine = self.engine
        self.window = self.window(gui)

    def test_three_pages(self):
        self.assertEqual(
            [page.title for page in self.window.pages],
            ["This computer", "lab.example", "Project ospf"],
        )
        self.assertEqual(
            self.window.pages[0].draft.keys, settings_window.WINDOWS
        )
        self.assertEqual(
            self.window.pages[1].draft.keys, settings_window.BRICKS
        )
        # the path there, as it is
        self.assertEqual(
            control(self.window, "workspace").get_text(), "/srv/labs"
        )

    def test_the_settings_there(self):
        window = self.window
        self.assertEqual(
            control(window, "audio_driver").get_text(), "pipewire"
        )
        self.assertTrue(
            control(window, "kernel_samepage_merging").get_active()
        )
        # typed, with the folders there to complete it
        entry = control(window, "qemu_path")
        self.assertTrue(entry.completer.folders)
        self.assertEqual(entry.get_text(), "/opt/qemu/bin")
        # those of the windows are this computer's
        self.assertEqual(
            control(window, "terminal").get_text(), get_setting("terminal")
        )
        self.assertEqual(self.facts.asked, [("/opt/vde/bin", "/opt/qemu/bin")])

    def test_ok(self):
        window = self.window
        audio_here = get_setting("audio_driver")
        control(window, "terminal").set_text("/usr/bin/foot")
        control(window, "audio_driver").set_text("pa")
        control(window, "qemu_path").set_text("/usr/local/bin")
        self.assertTrue(self.ok(window))
        # here
        self.assertEqual(get_setting("terminal"), "/usr/bin/foot")
        self.assertEqual(get_setting("audio_driver"), audio_here)
        self.assertEqual(
            load_toml(locations.settings_file())["terminal"], "/usr/bin/foot"
        )
        # there, in one call, what changed
        self.assertEqual(
            self.engine.sent,
            [
                (
                    "settings",
                    {"audio_driver": "pa", "qemu_path": "/usr/local/bin"},
                )
            ],
        )

    def test_ksm_there(self):
        control(self.window, "kernel_samepage_merging").set_active(False)
        self.ok(self.window)
        self.assertEqual(self.engine.sent[-1], ("ksm", False))

    def test_follows_there(self):
        copy = self.engine.factory
        copy.settings = dict(copy.settings, audio_driver="alsa")
        copy.settings_changed.notify(copy)
        self.assertEqual(
            control(self.window, "audio_driver").get_text(), "alsa"
        )

    def test_no_folder_there(self):
        self.facts.exists = False
        control(self.window, "qemu_path").set_text("/opt/qemu/bn")
        self.clock.advance(settings_window.FOLDER_DELAY)
        self.assertEqual(
            row(self.window, "qemu_path").problem.get_text(),
            "No folder /opt/qemu/bn on lab.example",
        )
