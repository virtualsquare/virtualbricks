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
The steps of the scenarios: what each line of a .feature file does.

A line runs the step whose words match it: ``When I start sw1`` runs
``start()``, with sw1 for ``{name:Brick}``. The words are those of parse:
``{seconds:d}`` takes a number, ``{name:Brick}`` the name of a brick,
``"{name}"`` a text in quotes. Two kinds of steps:

- The steps of a user say what the user does, in the words of Virtualbricks,
  and check what really happened, the processes of the bricks too.
- The steps of the screen click any widget, by its role and its name: for
  what the steps of a user don't say yet. A scenario that needs them often
  says that a step of a user is missing.

See README.md for how to add a step.
"""

import os
import shutil
import subprocess
import time

import pytest
from pytest_bdd import given, parsers, step, then, when

import harness


def brick(text):
    """The name of a brick: one word."""

    return text


# parse matches {name:Brick} with the pattern of the type
brick.pattern = r"[\w.-]+"


def words(text):
    """
    The words of a step, where {name:Brick} is the name of a brick, and
    {name:Project} that of a project.
    """

    return parsers.parse(text, extra_types={"Brick": brick, "Project": brick})


@pytest.fixture
def brick_processes():
    """The processes of each brick that a step started: {name: pids}."""

    return {}


# Virtualbricks


@given("Virtualbricks is running")
def virtualbricks_running(virtualbricks):
    virtualbricks.start()


@when("I start Virtualbricks for the first time")
def first_start(virtualbricks):
    """Without its settings, as after 2.1; it shows a window."""

    assert not os.path.exists(virtualbricks.settings), "it has its settings"
    virtualbricks.start()


@when("I start Virtualbricks again")
def start_again(virtualbricks):
    """With its settings, as after it ran before; it shows a window."""

    assert os.path.exists(virtualbricks.settings), "it has no settings"
    virtualbricks.start()


@when("I quit Virtualbricks")
def quit_virtualbricks(virtualbricks):
    virtualbricks.choose("Quit", "File")


@then("Virtualbricks has quit")
def virtualbricks_quit(virtualbricks):
    """It exits with 0, and no brick runs any more."""

    try:
        status = virtualbricks.process.wait(harness.QUIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise AssertionError(
            f"Virtualbricks still runs after {harness.QUIT_TIMEOUT} s"
        )
    assert status == 0, f"Virtualbricks exited with {status}"
    assert virtualbricks.bricks() == [], "bricks still run"


@then(words("the main window shows the project {name:Project}"))
def main_window(virtualbricks, name):
    """
    Its title names the project, and the workspace too when it isn't that of
    the settings.
    """

    workspace = os.path.join(
        "~", os.path.relpath(virtualbricks.workspace, virtualbricks.home)
    )
    titles = (
        f"Virtualbricks (project: {name})",
        f"Virtualbricks (project: {name}, workspace: {workspace})",
    )
    virtualbricks.wait_for(
        lambda: any(virtualbricks.shows("frame", title) for title in titles),
        f"the main window shows the project {name}",
    )


# Bricks


def new_brick(virtualbricks, kind, name):
    """New Brick, then the kind: the brick made is name, its settings show."""

    virtualbricks.click("button", "New Brick")
    # "virtual machine" is the row "Virtual machine"
    virtualbricks.click("label", kind[:1].upper() + kind[1:])
    virtualbricks.find("label", name)


@when(words("I add the {kind} {name:Brick}"))
def add_brick(virtualbricks, kind, name):
    """New Brick, then the kind; its settings, if any, as they are."""

    new_brick(virtualbricks, kind, name)
    if virtualbricks.shows("button", "OK"):
        virtualbricks.click("button", "OK")
    virtualbricks.find("button", f"Start {name}")


@when(
    words("I join {left:Brick} and {right:Brick} with the wire {name:Brick}")
)
def join(virtualbricks, left, right, name):
    """New Brick, Wire, then its ends in its settings: left, right; OK."""

    new_brick(virtualbricks, "wire", name)
    for end, switch in (("Left end", left), ("Right end", right)):
        row = virtualbricks.row(end)
        # named after the end it shows
        combo = virtualbricks.click("combo box", within=row)
        virtualbricks.click("menu item", switch, within=combo)
        virtualbricks.find("combo box", switch, within=row)
    virtualbricks.click("button", "OK")
    virtualbricks.find("button", f"Start {name}")


@when(words("I start {name:Brick}"))
def start_brick(virtualbricks, brick_processes, name):
    """Its button Start; then it runs, with new processes."""

    before = virtualbricks.children()
    virtualbricks.click("button", f"Start {name}")
    virtualbricks.find("button", f"Stop {name}")
    brick_processes[name] = virtualbricks.wait_for(
        lambda: virtualbricks.children() - before, f"a process of {name} runs"
    )


@when(words("I stop {name:Brick}"))
def stop_brick(virtualbricks, name):
    virtualbricks.click("button", f"Stop {name}")
    virtualbricks.find("button", f"Start {name}")


@then(words("{name:Brick} is running"))
@then(words("{name:Brick} is still running"))
def brick_running(virtualbricks, brick_processes, name):
    """Its row says so, and the processes of its start still run."""

    row = virtualbricks.row(name)
    virtualbricks.find("label", "Running", within=row)
    virtualbricks.find("button", f"Stop {name}", within=row)
    pids = brick_processes.get(name, set())
    assert pids <= virtualbricks.children(), f"the processes of {name} quit"


@then("the list of bricks has")
def bricks_listed(virtualbricks, datatable):
    """
    Its rows, all of them and in order, once they are those of the table
    under the step, whose first line has the titles of the columns: each
    row has the name of the brick, its detail and its state.
    """

    tab = virtualbricks.find("page tab", "Bricks")
    pane = virtualbricks.find("scroll pane", within=tab)

    def rows():
        return datatable[:1] + virtualbricks.rows(pane)

    try:
        virtualbricks.wait_for(
            lambda: rows() == datatable,
            "the list of bricks has the rows of the table",
        )
    except AssertionError:
        raise AssertionError(
            f"the list of bricks has {rows()}, not {datatable}"
        ) from None


@then(
    words(
        "{name:Brick} runs with the sockets of {left:Brick} and {right:Brick}"
    )
)
def runs_with_sockets(virtualbricks, brick_processes, name, left, right):
    """
    It runs, and the processes of its start have a vde_plug in the socket of
    each switch: the one its vde_switch listens on, after -s.
    """

    brick_running(virtualbricks, brick_processes, name)
    wanted = sorted(
        switch_socket(virtualbricks, brick_processes, switch)
        for switch in (left, right)
    )

    def plugs():
        found = []
        for pid in brick_processes[name]:
            for child in virtualbricks.children(pid):
                words = virtualbricks.command_line(child)
                if words and os.path.basename(words[0]) == "vde_plug":
                    found.append(words[-1])
        return sorted(found)

    try:
        virtualbricks.wait_for(
            lambda: plugs() == wanted,
            f"a vde_plug of {name} runs in the socket of {left}, another"
            f" in that of {right}",
        )
    except AssertionError:
        raise AssertionError(
            f"the vde_plug of {name} run in {plugs()}, not {wanted}"
        ) from None


def switch_socket(virtualbricks, brick_processes, switch):
    """The socket that the vde_switch of switch listens on, after -s."""

    for pid in brick_processes.get(switch, ()):
        words = virtualbricks.command_line(pid)
        if "-s" in words:
            return words[words.index("-s") + 1]
    raise AssertionError(f"no vde_switch of {switch} runs")


@then(words("{name:Brick} is stopped"))
@then(words("{name:Brick} is not running"))
def brick_stopped(virtualbricks, brick_processes, name):
    """
    Its row says so, and no process of it runs: neither those of its start
    nor any with its sockets, also if no step started it.
    """

    row = virtualbricks.row(name)
    virtualbricks.find("label", "Stopped", within=row)
    virtualbricks.find("button", f"Start {name}", within=row)
    pids = brick_processes.get(name, set())
    virtualbricks.wait_for(
        lambda: not pids & virtualbricks.children()
        and not virtualbricks.bricks(name),
        f"the processes of {name} quit",
    )


# Migration: the files of Virtualbricks 2.1

# The projects of 2.1 of the scenarios, each a folder with its .project
PROJECTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")
# ~/.virtualbricks.conf, as 2.1 wrote it; without the alert of missing
# programs, as the settings of the tests
SETTINGS_2_1 = """\
[Main]
show_missing = False
workspace = {workspace}
current_project = {project}
"""
MIGRATION = "Virtualbricks migration"


@given(words("the project {name:Project} of Virtualbricks 2.1"))
def old_project(virtualbricks, name):
    """A copy of projects/NAME, in the workspace."""

    shutil.copytree(
        os.path.join(PROJECTS, name),
        os.path.join(virtualbricks.workspace, name),
    )


@given(
    words("the settings of Virtualbricks 2.1, with {name:Project} open last")
)
def old_settings(virtualbricks, name):
    """
    Those of the workspace of the tests, in place of the settings of this
    version: the next start is the first.
    """

    os.remove(virtualbricks.settings)
    path = os.path.join(virtualbricks.home, ".virtualbricks.conf")
    with open(path, "w") as file:
        file.write(
            SETTINGS_2_1.format(
                workspace=virtualbricks.workspace, project=name
            )
        )


@then("the migration window shows")
def migration_window(virtualbricks):
    virtualbricks.find("frame", MIGRATION)


@then("the migration window doesn't show")
def no_migration_window(virtualbricks):
    virtualbricks.gone("frame", MIGRATION)


@then("the migration window lists")
def migration_lists(virtualbricks, datatable):
    """
    The rows of its list, all of them and in order, once they are those of
    the table under the step, whose first line has the titles of the
    columns.
    """

    window = virtualbricks.find("frame", MIGRATION)
    table = virtualbricks.find("table", within=window)

    def rows():
        titles = virtualbricks.names("table column header", within=table)
        cells = virtualbricks.names("table cell", within=table)
        width = len(titles)
        return [titles] + [
            cells[start : start + width]
            for start in range(0, len(cells), width)
        ]

    try:
        virtualbricks.wait_for(
            lambda: rows() == datatable,
            "the migration window lists the rows of the table",
        )
    except AssertionError:
        raise AssertionError(
            f"the migration window lists {rows()}, not {datatable}"
        ) from None


@then(words("{name:Project} is migrated"))
def migrated(virtualbricks, name):
    """
    The migration ends, as Save report… says, no row of the window failed,
    and the project has the file of this version.
    """

    window = virtualbricks.find("frame", MIGRATION)
    virtualbricks.enabled("button", "Save report…", within=window)
    failed = virtualbricks.shows("table cell", "✗ Failed", within=window)
    assert failed is None, "the migration window says it failed"
    path = os.path.join(virtualbricks.workspace, name, "project.toml")
    assert os.path.isfile(path), f"{path} is missing"


@when("I close the migration window")
def close_migration(virtualbricks):
    """
    Its button Close, beside Save report…: that of the title bar comes
    first.
    """

    window = virtualbricks.find("frame", MIGRATION)
    save = virtualbricks.find("button", "Save report…", within=window)
    virtualbricks.click("button", "Close", within=save.get_parent())
    virtualbricks.gone("frame", MIGRATION)


@given(words("Virtualbricks migrated {name:Project} at its first start"))
def migrated_at_first_start(virtualbricks, name):
    """It starts, the migration of name ends, and its window is closed."""

    first_start(virtualbricks)
    migrated(virtualbricks, name)
    close_migration(virtualbricks)


# Time


@when(words("I wait {seconds:d} seconds"))
def wait(seconds):
    time.sleep(seconds)


# The screen: any widget, by role and name, as the dump of the widgets
# shows them


@when(words('I click the {role} "{name}"'))
def click(virtualbricks, role, name):
    virtualbricks.click(role, name)


@when(words('I choose "{item}" in the menu "{menu}"'))
def choose(virtualbricks, item, menu):
    virtualbricks.choose(item, menu)


@then(words('the {role} "{name}" shows'))
def shows(virtualbricks, role, name):
    virtualbricks.find(role, name)


@then(words('the {role} "{name}" doesn\'t show'))
def doesnt_show(virtualbricks, role, name):
    virtualbricks.gone(role, name)


@step("I print the widgets")
def print_widgets(virtualbricks):
    """The widgets that show, for pytest -s: their roles and names."""

    print(virtualbricks.describe())
