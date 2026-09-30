# -*- test-case-name: virtualbricks.tests.console.test_projects -*-
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
The commands of the projects: project list, show, open, new, save, rename,
duplicate and delete, on the workspace.

Opening and saving go through the front end, ``frontend``: without the
windows, the workspace itself; with them, the main window, which saves what
its tabs hold and shows the project that opens. The GUI sets it with
``use_frontend()``.
"""

from __future__ import annotations

from virtualbricks.config.workspace import projects
from virtualbricks.console.command import (
    Arg,
    ArgKind,
    CommandError,
    Flag,
    command,
)
from virtualbricks.console.output import table
from virtualbricks.i18n import N_, _, ngettext
from virtualbricks.bricks import is_running


class Frontend:
    """How the console opens, makes and saves projects, without windows."""

    def open(self, name, factory):
        """Open a project; return the report of reading it."""

        return projects.open(name, factory)

    def new(self, name, factory):
        projects.create(name)
        return projects.open(name, factory)

    def save(self, factory):
        projects.save(factory)


frontend = Frontend()


def use_frontend(new):
    """The front end the console opens and saves projects through."""

    global frontend
    frontend = new


class ProjectName(ArgKind):
    def read(self, context, word):
        if not projects.exists(word):
            raise CommandError(_("No project named {name}").format(name=word))
        return word

    def candidates(self, context, done):
        return projects.names()


PROJECT = ProjectName()


def refuse_running(factory):
    """CommandError if bricks run: the project can't change under them."""

    from virtualbricks.bricks.eventinfo import names

    running = [brick.name for brick in factory.bricks if is_running(brick)]
    if running:
        raise CommandError(
            ngettext(
                "{names} is running: stop it first",
                "{names} are running: stop them first",
                len(running),
            ).format(names=names(running))
        )


def _check(name, renaming=None):
    reason = projects.check_name(name, renaming=renaming)
    if reason is not None:
        raise CommandError(f"{name}: {reason}")


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip().lstrip("#").strip()
    return ""


@command("project", "list", help=N_("The projects of the workspace"))
def list_(context):
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
def show(context):
    current = projects.current
    if current is None:
        return [_("No project is open")]
    factory = context.factory
    return [
        current.name,
        current.path,
        _("{bricks} bricks, {events} events, {images} images").format(
            bricks=len(factory.bricks),
            events=len(list(factory.iter_events())),
            images=len(list(factory.iter_disk_images())),
        ),
    ]


def _report(report):
    return [str(message) for message in report.messages]


@command(
    "project",
    "open",
    Arg("NAME", PROJECT),
    help=N_("Save the open project and open another"),
)
def open_(context, name):
    refuse_running(context.factory)
    return _report(frontend.open(name, context.factory))


@command(
    "project",
    "new",
    Arg("NAME"),
    help=N_("Save the open project, make a new one and open it"),
)
def new(context, name):
    refuse_running(context.factory)
    _check(name)
    frontend.new(name, context.factory)


@command("project", "save", help=N_("Save the open project now"))
def save(context):
    frontend.save(context.factory)


@command(
    "project",
    "rename",
    Arg("NAME", PROJECT),
    Arg("NEW"),
    help=N_("Rename a project"),
)
def rename(context, name, new):
    _check(new, renaming=name)
    projects.rename(name, new)


@command(
    "project",
    "duplicate",
    Arg("NAME", PROJECT),
    Arg("NEW"),
    help=N_("Copy a project, its disks included"),
)
def duplicate(context, name, new):
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
def delete(context, name, force):
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
