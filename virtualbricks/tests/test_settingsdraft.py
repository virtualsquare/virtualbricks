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

"""The drafts of the Settings window, and what they check."""

import attr
from twisted.trial import unittest

from virtualbricks.bricks.draft import Problem
from virtualbricks.config.schema import dump_record
from virtualbricks.config.settings import AppSettings, ProjectSettings
from virtualbricks.programs import REQUIRED, FolderPrograms, Missing
from virtualbricks.settingsdraft import (
    TERMINALS,
    Facts,
    Owner,
    SettingsDraft,
    audio_drivers,
    terminals,
)


def owner(record, **values):
    """An owner of the defaults, but values; what OK writes, in written."""

    settings = {**dump_record(record()), **values}
    owner = Owner(record, settings.__getitem__)
    owner.written = []
    owner.write = owner.written.append
    return owner


def vde(folder="/usr/bin", missing=(), elsewhere=(), exists=True):
    found = {
        name: f"/elsewhere/{name}" if name in elsewhere else f"{folder}/{name}"
        for name in REQUIRED
        if name not in missing
    }
    return FolderPrograms(
        folder,
        exists,
        found,
        tuple(Missing(name, "vde2") for name in missing),
    )


def qemu(folder="/usr/bin", emulators=("x86_64",), img=True, exists=True):
    names = (["qemu-img"] if img else []) + [
        f"qemu-system-{name}" for name in emulators
    ]
    missing = () if img else (Missing("qemu-img", "qemu-utils"),)
    return FolderPrograms(
        folder, exists, {name: f"{folder}/{name}" for name in names}, missing
    )


class TestTables(unittest.TestCase):

    def test_terminals(self):
        found = {"xterm", "konsole", "gnome-terminal"}
        self.assertEqual(
            terminals(lambda name: name if name in found else None),
            ["xterm", "konsole"],
        )
        # the terminal of the desktop first
        self.assertEqual(TERMINALS[0], "x-terminal-emulator")

    def test_audio_drivers(self):
        # QEMU 10.0 of Debian 13
        drivers = "alsa dbus jack none oss pa pipewire sdl wav".split()
        self.assertEqual(
            audio_drivers(drivers),
            (
                ["pipewire", "pa", "alsa", "jack", "oss", "sdl"],
                ["dbus", "none", "wav"],
            ),
        )


class TestDraft(unittest.TestCase):

    def test_read(self):
        draft = SettingsDraft(owner(ProjectSettings, qemu_path="/opt/qemu"))
        self.assertEqual(draft.get("qemu_path"), "/opt/qemu")
        self.assertEqual(
            draft.keys,
            ("log_link_loops", "allow_female_plugs", "qemu_path", "vde_path"),
        )
        self.assertEqual(draft.changes(), {})
        self.assertEqual(draft.problems(), [])

    def test_changes_and_ok(self):
        project = owner(ProjectSettings)
        draft = SettingsDraft(project)
        draft.set("log_link_loops", True)
        draft.set("qemu_path", "/opt/qemu")
        changes = draft.changes()
        self.assertEqual(
            changes, {"log_link_loops": True, "qemu_path": "/opt/qemu"}
        )
        draft.give(changes)
        self.assertEqual(project.written, [changes])
        # OK wrote them: the draft starts from them
        draft.saved()
        self.assertEqual(draft.changes(), {})
        draft.set("log_link_loops", False)
        self.assertEqual(draft.changes(), {"log_link_loops": False})

    def test_follow_a_setting_untouched(self):
        draft = SettingsDraft(owner(AppSettings))
        self.assertTrue(draft.follow("terminal", "/usr/bin/foot"))
        self.assertEqual(draft.get("terminal"), "/usr/bin/foot")
        # nothing for OK to write
        self.assertEqual(draft.changes(), {})

    def test_follow_a_setting_changed_here(self):
        draft = SettingsDraft(owner(AppSettings))
        draft.set("terminal", "xterm")
        # the window's stays, and OK writes it: the last OK wins
        self.assertFalse(draft.follow("terminal", "/usr/bin/foot"))
        self.assertEqual(draft.get("terminal"), "xterm")
        self.assertEqual(draft.changes(), {"terminal": "xterm"})
        # the same as the window's: nothing to write
        draft.follow("terminal", "xterm")
        self.assertEqual(draft.changes(), {})

    def test_follow_a_setting_typed_wrong(self):
        draft = SettingsDraft(owner(AppSettings))
        draft.set("tray_icon", "maybe")
        self.assertFalse(draft.follow("tray_icon", False))
        self.assertEqual(draft.get("tray_icon"), "maybe")

    def test_follow_another_record(self):
        draft = SettingsDraft(owner(ProjectSettings))
        self.assertFalse(draft.follow("terminal", "xterm"))

    def test_failed(self):
        draft = SettingsDraft(owner(AppSettings))
        draft.set("kernel_samepage_merging", True)
        draft.fail("kernel_samepage_merging", "KSM is still off")
        self.assertEqual(
            draft.errors(),
            [Problem("kernel_samepage_merging", "KSM is still off")],
        )
        # until it is set again
        draft.set("kernel_samepage_merging", True)
        self.assertEqual(draft.errors(), [])


class TestTerminal(unittest.TestCase):

    def setUp(self):
        self.draft = SettingsDraft(owner(AppSettings))
        self.programs = {"xterm": "/usr/bin/xterm"}
        self.draft.facts = Facts(which=self.programs.get)

    def test_found(self):
        self.draft.set("terminal", "xterm")
        self.assertEqual(self.draft.problems(), [])

    def test_not_found(self):
        self.draft.set("terminal", "foot")
        self.assertEqual(
            self.draft.problems(),
            [
                Problem(
                    "terminal",
                    "No program foot on this computer: the consoles of the"
                    " bricks can't open",
                    error=False,
                )
            ],
        )

    def test_none(self):
        self.draft.set("terminal", "")
        [problem] = self.draft.problems()
        self.assertEqual(
            problem.text, "No terminal: the consoles of the bricks can't open"
        )
        self.assertFalse(problem.error)

    def test_not_on_its_page(self):
        # the machine of the bricks, another: its terminal isn't its page's
        draft = SettingsDraft(
            owner(AppSettings, terminal="foot"),
            ("kernel_samepage_merging", "audio_driver", "workspace"),
        )
        draft.facts = Facts(which=self.programs.get)
        self.assertEqual(draft.problems(), [])


class TestAudioDriver(unittest.TestCase):

    def setUp(self):
        self.draft = SettingsDraft(owner(AppSettings, audio_driver="sndio"))

    def test_unknown_yet(self):
        self.assertEqual(self.draft.problems(), [])
        self.assertEqual(self.draft.note("audio_driver"), "")

    def test_not_listed(self):
        self.draft.facts = Facts(
            qemu_version="10.0.11",
            audio_drivers=frozenset({"alsa", "pa", "pipewire"}),
        )
        self.assertEqual(
            self.draft.problems(),
            [
                Problem(
                    "audio_driver",
                    "QEMU 10.0.11 has no audio driver sndio: a machine with a"
                    " sound card starts without it",
                    error=False,
                )
            ],
        )
        self.draft.set("audio_driver", "pipewire")
        self.assertEqual(self.draft.problems(), [])

    def test_qemu_6_2(self):
        # it lists none: taken on trust
        self.draft.facts = Facts(qemu_version="6.2.0", audio_drivers=None)
        self.assertEqual(self.draft.problems(), [])
        self.assertEqual(
            self.draft.note("audio_driver"),
            "QEMU 6.2.0 doesn't list its drivers: this one is taken on trust",
        )


class TestKsm(unittest.TestCase):

    def test_available(self):
        draft = SettingsDraft(owner(AppSettings))
        draft.facts = Facts(ksm_available=True)
        self.assertTrue(draft.uses("kernel_samepage_merging"))
        self.assertEqual(draft.note("kernel_samepage_merging"), "")

    def test_missing(self):
        draft = SettingsDraft(owner(AppSettings))
        draft.facts = Facts(ksm_available=False)
        self.assertFalse(draft.uses("kernel_samepage_merging"))
        self.assertEqual(
            draft.note("kernel_samepage_merging"), "This Linux has no KSM"
        )

    def test_missing_but_on(self):
        # it can be turned off
        draft = SettingsDraft(owner(AppSettings, kernel_samepage_merging=True))
        draft.facts = Facts(ksm_available=False, where="lab.example")
        self.assertTrue(draft.uses("kernel_samepage_merging"))
        self.assertEqual(
            draft.note("kernel_samepage_merging"), "lab.example has no KSM"
        )


class TestFolders(unittest.TestCase):

    def setUp(self):
        self.draft = SettingsDraft(owner(ProjectSettings))

    def test_unknown_yet(self):
        self.assertEqual(self.draft.problems(), [])
        self.assertEqual(self.draft.note("qemu_path"), "")

    def test_all_here(self):
        self.draft.facts = Facts(
            vde=vde(),
            qemu=qemu(emulators=("amd64", "i386", "x86_64")),
            qemu_version="10.0.11",
        )
        self.assertEqual(self.draft.problems(), [])
        self.assertEqual(
            self.draft.note("qemu_path"),
            "QEMU 10.0.11: qemu-img and qemu-system-amd64, i386 and x86_64",
        )
        self.assertEqual(
            self.draft.note("vde_path"),
            "The 9 VDE programs of the bricks are here",
        )

    def test_many_emulators(self):
        emulators = ("aarch64", "arm", "i386", "mips", "ppc", "x86_64")
        self.draft.facts = Facts(qemu=qemu(emulators=emulators))
        # the version isn't known yet
        self.assertEqual(
            self.draft.note("qemu_path"), "qemu-img and 6 emulators"
        )

    def test_facts_of_another_folder(self):
        # asked for the folder before the one typed
        self.draft.set("qemu_path", "/opt/qemu")
        self.draft.facts = Facts(qemu=qemu(img=False))
        self.assertEqual(self.draft.problems(), [])
        self.assertEqual(self.draft.note("qemu_path"), "")

    def test_no_folder(self):
        self.draft.set("qemu_path", "/opt/qemu")
        self.draft.facts = Facts(qemu=qemu("/opt/qemu", exists=False))
        self.assertEqual(
            self.draft.errors(), [Problem("qemu_path", "No folder /opt/qemu")]
        )
        self.assertEqual(self.draft.note("qemu_path"), "")

    def test_no_folder_there(self):
        self.draft.set("qemu_path", "/opt/qemu")
        self.draft.facts = Facts(
            qemu=qemu("/opt/qemu", exists=False), where="lab.example"
        )
        [problem] = self.draft.errors()
        self.assertEqual(problem.text, "No folder /opt/qemu on lab.example")

    def test_missing(self):
        self.draft.facts = Facts(vde=vde(missing=("vde_cryptcab",)))
        self.assertEqual(
            self.draft.problems(),
            [
                Problem(
                    "vde_path",
                    "Missing here and in PATH: vde_cryptcab (vde2)",
                    error=False,
                )
            ],
        )
        # the problem says it
        self.assertEqual(self.draft.note("vde_path"), "")

    def test_in_path(self):
        self.draft.facts = Facts(
            vde=vde(elsewhere=("vde_switch", "vde_plug")),
            qemu=attr.evolve(
                qemu(), found={"qemu-img": "/elsewhere/qemu-img"}
            ),
        )
        self.assertEqual(
            self.draft.note("vde_path"),
            "In PATH, not here: vde_switch and vde_plug",
        )
        self.assertEqual(
            self.draft.note("qemu_path"),
            "qemu-img; in PATH, not here: qemu-img",
        )

    def test_path_alone(self):
        self.draft.set("vde_path", "")
        self.draft.set("qemu_path", "")
        self.draft.facts = Facts(
            vde=vde(folder=""), qemu=qemu(folder="", img=False)
        )
        self.assertEqual(
            self.draft.note("vde_path"),
            "The 9 VDE programs of the bricks are in PATH",
        )
        self.assertEqual(
            self.draft.problems(),
            [
                Problem(
                    "qemu_path",
                    "Missing in PATH: qemu-img (qemu-utils)",
                    error=False,
                )
            ],
        )
