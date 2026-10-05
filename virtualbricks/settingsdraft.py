# -*- test-case-name: virtualbricks.tests.test_settingsdraft -*-
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
The settings of the Settings window, until OK (page 23 §6).

The window has a draft for each owner of settings, on a page of its own:
this computer, whose settings are in its settings.toml; the machine of the
bricks, when it is another; and the open project. A draft holds a copy of
its owner's settings and the values as the rows have them, as the drafts of
the bricks do, and OK writes its ``changes()``, nothing else. A draft checks
the settings of its page, its ``keys``, and no other.

Some checks need facts: what the folders of the programs hold and the audio
drivers that QEMU lists, which the window asks the engine for, and the
programs of this computer, for the terminal. The window gives them to the
drafts as ``facts``, and they check against what they have, so ``check()``
waits for nothing; until the facts come, a row has no note and no problem.

A setting changed elsewhere while the window is open, in the console or by
the Virtualbricks there, reaches a draft with ``follow()``: one that the
window hasn't changed takes the new value, and one that it has keeps the
window's, which OK writes (19 R7 B).

Nothing here imports GTK.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable, Sequence

import attr

from virtualbricks.bricks.draft import Draft, Problem, copy
from virtualbricks.bricks.eventinfo import names
from virtualbricks.config.schema import field_names
from virtualbricks.i18n import _
from virtualbricks.programs import FolderPrograms

# The terminals that take -e followed by a program and its arguments, as a
# console needs, on every target (page 23 §9): x-terminal-emulator, that of
# the desktop, first. gnome-terminal, xfce4-terminal and mate-terminal take
# one string after -e; x-terminal-emulator reaches them through a wrapper.
TERMINALS = (
    "x-terminal-emulator",
    "xterm",
    "uxterm",
    "konsole",
    "ptyxis",
    "lxterminal",
    "qterminal",
)
# The audio drivers of QEMU that play the sound on the computer of the
# machines, in the order the Settings window offers them; the others, as
# wav or none, come after.
PLAYING = ("pipewire", "pa", "alsa", "jack", "oss", "sdl", "sndio")
# The emulators a note names one by one; more are counted.
EMULATORS_NAMED = 5
QEMU_SYSTEM = "qemu-system-"


def terminals(which: Callable[[str], str | None] = shutil.which) -> list[str]:
    """The terminals of TERMINALS that this computer has."""

    return [name for name in TERMINALS if which(name)]


def audio_drivers(drivers: Iterable[str]) -> tuple[list[str], list[str]]:
    """Those of drivers that play the sound, in PLAYING's order; the others."""

    drivers = set(drivers)
    playing = [driver for driver in PLAYING if driver in drivers]
    return playing, sorted(drivers - set(playing))


@attr.define(frozen=True)
class Facts:
    """What the drafts check against; None, or empty, while not known."""

    # what the folders hold, each as it was asked for its folder
    vde: FolderPrograms | None = None
    qemu: FolderPrograms | None = None
    # the version of the QEMU of the folder, as "10.0.11", and its audio
    # drivers, None if it lists none, as QEMU 6.2
    qemu_version: str = ""
    audio_drivers: frozenset[str] | None = None
    # whether the machine of the bricks has KSM
    ksm_available: bool | None = None
    # the machine of the bricks, when it is another
    where: str = ""
    # the programs of this computer, for the terminal
    which: Callable[[str], str | None] = shutil.which


class Owner:
    """
    Whose settings a draft has: the record of their schema, where each one
    is read, and what writes those that OK changed.
    """

    def __init__(
        self,
        record: type,
        setting: Callable[[str], object],
        write: Callable[[dict[str, object]], object] = lambda changes: None,
    ) -> None:
        self.record = record
        self.setting = setting
        self.write = write

    def read(self):
        return self.record(
            **{name: self.setting(name) for name in field_names(self.record)}
        )


class SettingsDraft(Draft):
    """The settings of an owner, as its page has them, until OK."""

    def __init__(self, owner: Owner, keys: Sequence[str] = ()) -> None:
        # the settings of the page; the others stay as the owner has them
        self.keys = tuple(keys) or tuple(field_names(owner.record))
        self.facts = Facts()
        # the settings that OK couldn't change, as KSM, and why: warnings,
        # since OK tries again, until they are set again
        self.failed: dict[str, str] = {}
        super().__init__(owner)

    def read(self):
        return self.brick.read()

    def give(self, changes: dict[str, object]):
        """Write the settings that changed; what the owner's write gives."""

        return self.brick.write(changes)

    def set(self, name: str, value: object) -> None:
        self.failed.pop(name, None)
        super().set(name, value)

    def follow(self, name: str, value: object) -> bool:
        """
        A setting changed elsewhere: the draft takes it, unless the window
        changed it; whether the row has another value to show.
        """

        if name not in field_names(self.settings):
            return False
        changed = name in self.refused or getattr(
            self.settings, name
        ) != getattr(self.original, name)
        setattr(self.original, name, value)
        if changed:
            return False
        setattr(self.settings, name, value)
        return True

    def saved(self) -> None:
        """OK wrote the changes: the draft starts from them."""

        self.original = copy(self.settings)

    def fail(self, name: str, text: str) -> None:
        """OK couldn't change a setting, for the reason of text."""

        self.failed[name] = text

    # What the rows say

    def uses(self, name: str) -> bool:
        if (
            name == "kernel_samepage_merging"
            and self.facts.ksm_available is False
        ):
            # turned off, if it is on
            return bool(getattr(self.original, name))
        return super().uses(name)

    def note(self, name: str) -> str:
        facts = self.facts
        if name == "kernel_samepage_merging" and facts.ksm_available is False:
            if facts.where:
                return _("{where} has no KSM").format(where=facts.where)
            return _("This Linux has no KSM")
        if (
            name == "audio_driver"
            and facts.qemu_version
            and facts.audio_drivers is None
        ):
            # QEMU 6.2
            return _(
                "QEMU {version} doesn't list its drivers: this one is taken on"
                " trust"
            ).format(version=facts.qemu_version)
        if name == "qemu_path":
            return self._qemu_note()
        if name == "vde_path":
            return self._vde_note()
        return ""

    def _folder(self, name: str) -> FolderPrograms | None:
        """The facts of the folder of the setting, if they are its value's."""

        found = getattr(self.facts, name.removesuffix("_path"))
        if found is None or found.folder != self.get(name) or not found.exists:
            return None
        return found

    def _elsewhere(self, found: FolderPrograms) -> list[str]:
        """The programs found in PATH, not in the folder of the setting."""

        return found.elsewhere() if found.folder else []

    def _qemu_note(self) -> str:
        found = self._folder("qemu_path")
        if found is None or not found.found:
            return ""
        programs = [name for name in found.found if name == "qemu-img"]
        emulators = [
            name.removeprefix(QEMU_SYSTEM) for name in found.emulators()
        ]
        if len(emulators) > EMULATORS_NAMED:
            programs.append(
                _("{count} emulators").format(count=len(emulators))
            )
        elif emulators:
            programs.append(QEMU_SYSTEM + names(emulators))
        text = names(programs)
        if self.facts.qemu_version:
            text = _("QEMU {version}: {programs}").format(
                version=self.facts.qemu_version, programs=text
            )
        elsewhere = self._elsewhere(found)
        if elsewhere:
            text = _("{note}; in PATH, not here: {programs}").format(
                note=text, programs=names(elsewhere)
            )
        return text

    def _vde_note(self) -> str:
        found = self._folder("vde_path")
        if found is None:
            return ""
        elsewhere = self._elsewhere(found)
        if elsewhere:
            return _("In PATH, not here: {programs}").format(
                programs=names(elsewhere)
            )
        if found.missing:
            # the problem says what is missing
            return ""
        if not found.folder:
            return _(
                "The {count} VDE programs of the bricks are in PATH"
            ).format(count=len(found.found))
        return _("The {count} VDE programs of the bricks are here").format(
            count=len(found.found)
        )

    def check(self) -> list[Problem]:
        problems = []
        for name in self.keys:
            if name in self.failed:
                problems.append(Problem(name, self.failed[name], error=False))
                continue
            check = getattr(self, f"_check_{name}", None)
            if check is None or name in self.refused:
                continue
            problem = check(name, self.get(name))
            if problem is not None:
                problems.append(problem)
        return problems

    def _check_terminal(self, name: str, terminal) -> Problem | None:
        if not terminal:
            text = _("No terminal: the consoles of the bricks can't open")
        elif self.facts.which(terminal) is None:
            text = _(
                "No program {terminal} on this computer: the consoles of the"
                " bricks can't open"
            ).format(terminal=terminal)
        else:
            return None
        return Problem(name, text, error=False)

    def _check_audio_driver(self, name: str, driver) -> Problem | None:
        drivers = self.facts.audio_drivers
        if not self.facts.qemu_version or drivers is None or driver in drivers:
            return None
        return Problem(
            name,
            _(
                "QEMU {version} has no audio driver {driver}: a machine with a"
                " sound card starts without it"
            ).format(version=self.facts.qemu_version, driver=driver),
            error=False,
        )

    def _check_folder(self, name: str, folder) -> Problem | None:
        found = getattr(self.facts, name.removesuffix("_path"))
        if found is None or found.folder != folder:
            return None
        if not found.exists:
            if self.facts.where:
                text = _("No folder {folder} on {where}").format(
                    folder=folder, where=self.facts.where
                )
            else:
                text = _("No folder {folder}").format(folder=folder)
            return Problem(name, text)
        if not found.missing:
            return None
        missing = names([str(program) for program in found.missing])
        if folder:
            text = _("Missing here and in PATH: {programs}")
        else:
            text = _("Missing in PATH: {programs}")
        return Problem(name, text.format(programs=missing), error=False)

    _check_qemu_path = _check_folder
    _check_vde_path = _check_folder
