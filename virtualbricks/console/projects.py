# -*- test-case-name: virtualbricks.tests.console.test_projects -*-
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

"""
The commands of the projects: project list, show, open, new, save, rename,
duplicate and delete, on the workspace.

Opening and saving go through the front end, ``frontend``: without the
windows, the workspace itself; with them, the main window, which saves what
its tabs hold and shows the project that opens. The GUI sets it with
``use_frontend()``.
"""

from __future__ import annotations

from typing import Protocol

from virtualbricks.brickfactory import BrickFactory
from virtualbricks.config.report import Report
from virtualbricks.config.workspace import projects
from virtualbricks.console.command import (
    Arg,
    ArgKind,
    CommandError,
    Context,
    Flag,
    NotFound,
    command,
)
from virtualbricks.console.output import table
from virtualbricks.i18n import N_, _, ngettext
from virtualbricks.bricks import must_stop


class Frontend(Protocol):
    """How the console opens, makes and saves projects."""

    def open(self, name: str, factory: BrickFactory) -> Report:
        """Open a project; return the report of reading it."""

    def new(self, name: str, factory: BrickFactory) -> None:
        """Make a project and open it."""

    def save(self, factory: BrickFactory) -> None:
        """Save the open project."""


class WorkspaceFrontend:
    """How the console opens, makes and saves projects, without windows."""

    def open(self, name: str, factory: BrickFactory) -> Report:
        return projects.open(name, factory)

    def new(self, name: str, factory: BrickFactory) -> None:
        projects.create(name)
        projects.open(name, factory)

    def save(self, factory: BrickFactory) -> None:
        projects.save(factory)


frontend: Frontend = WorkspaceFrontend()


def use_frontend(new: Frontend) -> None:
    """The front end the console opens and saves projects through."""

    global frontend
    frontend = new


class ProjectName(ArgKind):
    def read(self, context: Context, word: str) -> str:
        if not projects.exists(word):
            raise NotFound(_("No project named {name}").format(name=word))
        return word

    def candidates(self, context: Context, done: dict) -> list[str]:
        return projects.names()


PROJECT = ProjectName()


def refuse_running(factory: BrickFactory) -> None:
    """CommandError if bricks run: the project can't change under them."""

    from virtualbricks.bricks.eventinfo import names

    running = [brick.name for brick in factory.bricks if must_stop(brick)]
    if running:
        raise CommandError(
            ngettext(
                "{names} is running: stop it first",
                "{names} are running: stop them first",
                len(running),
            ).format(names=names(running))
        )


def _check(name: str, renaming: str | None = None) -> None:
    reason = projects.check_name(name, renaming=renaming)
    if reason is not None:
        raise CommandError(f"{name}: {reason}")


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip().lstrip("#").strip()
    return ""


@command("project", "list", help=N_("The projects of the workspace"))
def list_(context: Context) -> list[str]:
    current = projects.current.name if projects.current else None
    rows = [
        (
            ("* " if summary.name == current else "  ") + summary.name,
            _first_line(summary.description) or summary.problem or "",
        )
        for summary in sorted(projects.summaries(), key=lambda s: s.name)
    ]
    if not rows:
        return [_("No projects")]
    return table(rows)


@command("project", "show", help=N_("The open project"))
def show(context: Context) -> list[str]:
    current = projects.current
    if current is None:
        return [_("No project is open")]
    factory = context.factory
    return [
        current.name,
        current.path,
        _("{bricks} bricks, {events} events, {images} images").format(
            bricks=len(list(factory.bricks)),
            events=len(list(factory.events)),
            images=len(list(factory.images)),
        ),
    ]


def _report(report: Report) -> list[str]:
    return [str(message) for message in report.messages]


@command(
    "project",
    "open",
    Arg("NAME", PROJECT),
    help=N_("Save the open project and open another"),
)
def open_(context: Context, name: str) -> list[str]:
    refuse_running(context.factory)
    return _report(frontend.open(name, context.factory))


@command(
    "project",
    "new",
    Arg("NAME"),
    help=N_("Save the open project, make a new one and open it"),
)
def new(context: Context, name: str) -> None:
    refuse_running(context.factory)
    _check(name)
    frontend.new(name, context.factory)


@command("project", "save", help=N_("Save the open project now"))
def save(context: Context) -> None:
    frontend.save(context.factory)


@command(
    "project",
    "rename",
    Arg("NAME", PROJECT),
    Arg("NEW"),
    help=N_("Rename a project"),
)
def rename(context: Context, name: str, new: str) -> None:
    _check(new, renaming=name)
    projects.rename(name, new)


@command(
    "project",
    "duplicate",
    Arg("NAME", PROJECT),
    Arg("NEW"),
    help=N_("Copy a project, its disks included"),
)
def duplicate(context: Context, name: str, new: str) -> None:
    _check(new)
    projects.duplicate(name, new)


@command(
    "project",
    "delete",
    Arg("NAME", PROJECT),
    flags=[Flag("force")],
    help=N_(
        "Move a project to the trash; without one, --force deletes it for"
        " good"
    ),
)
def delete(context: Context, name: str, force: bool) -> list[str]:
    if projects.current is not None and projects.current.name == name:
        raise CommandError(
            _("{name} is open: open another first").format(name=name)
        )
    if projects.can_trash(name):
        projects.trash(name)
        return [_("{name} is in the trash").format(name=name)]
    if not force:
        raise CommandError(
            _(
                "There is no trash here: --force deletes {name} for good"
            ).format(name=name)
        )
    projects.delete(name)
    return []
