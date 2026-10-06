# -*- test-case-name: virtualbricks.tests.console.test_settings -*-
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
The commands of the settings: those of Virtualbricks, in settings.toml, and
those of the open project, as the two tabs of the Settings window.
"""

from __future__ import annotations

from typing import cast

from virtualbricks.config.schema import field_default, field_names
from virtualbricks.config.settings import (
    PROJECT_KEYS,
    AppSettings,
    ProjectSettings,
    SettingValue,
    get_setting,
    has_option,
    parse_setting,
    set_setting,
    setting_kind,
    store_settings,
)
from virtualbricks.console.command import (
    Arg,
    ArgKind,
    CommandError,
    Context,
    KeyValues,
    command,
)
from virtualbricks.i18n import N_, _


def _names() -> list[str]:
    return field_names(AppSettings) + field_names(ProjectSettings)


class Key(ArgKind):
    def read(self, context: Context, word: str) -> str:
        if not has_option(word):
            raise CommandError(
                _("No setting {key}: setting show lists them").format(key=word)
            )
        return word

    def candidates(self, context: Context, done: dict) -> list[str]:
        return _names()


def _line(name: str) -> str:
    return f"{name} = {setting_kind(name).format(get_setting(name))}"


def _set(values: dict[str, SettingValue]) -> None:
    """Set the settings of values, a dict, and write settings.toml."""

    for name, value in values.items():
        try:
            set_setting(name, value)
        except ValueError as exc:
            raise CommandError(str(exc)) from None
    if any(name not in PROJECT_KEYS for name in values):
        store_settings()


@command(
    "setting",
    "show",
    Arg("KEY", Key(), optional=True),
    help=N_("The settings of Virtualbricks and of the open project"),
)
def show(context: Context, key: str | None) -> list[str]:
    if key is not None:
        return [_line(key)]
    lines = [_("# Virtualbricks")]
    lines += [_line(name) for name in field_names(AppSettings)]
    lines += ["", _("# This project")]
    lines += [_line(name) for name in field_names(ProjectSettings)]
    return lines


@command(
    "setting",
    "set",
    Arg(
        "KEY=VALUE",
        KeyValues(
            lambda context, done: _names(),
            lambda context, done, key: (
                setting_kind(key) if has_option(key) else None
            ),
        ),
        many=True,
    ),
    help=N_("Change settings, all or none"),
    example="setting set terminal=/usr/bin/gnome-terminal",
)
def set_(context: Context, key_value: list[tuple[str, str]]) -> None:
    values = {}
    for name, text in key_value:
        Key().read(context, name)
        try:
            values[name] = parse_setting(name, text)
        except ValueError as exc:
            reason = str(exc).removeprefix(f"{name}: ")
            raise CommandError(f"{name}: {reason}") from None
    _set(values)


@command(
    "setting",
    "unset",
    Arg("KEY", Key(), many=True),
    help=N_("Put settings back to their defaults"),
)
def unset(context: Context, key: list[str]) -> None:
    values = {}
    for name in key:
        owner = ProjectSettings if name in PROJECT_KEYS else AppSettings
        # a setting is a string or a boolean
        values[name] = cast(SettingValue, field_default(owner, name))
    _set(values)
