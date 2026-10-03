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

See STEPS.md for the steps there are, and how to add one.
"""

import configparser
import glob
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
import types
import urllib.parse

try:
    import tomllib
except ImportError:
    # before Python 3.11
    import tomli as tomllib

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
    The words of a step, where {name:Brick} is the name of a brick,
    {name:Project} that of a project, and {name:Image} that of a disk image.
    """

    return parsers.parse(
        text, extra_types={"Brick": brick, "Project": brick, "Image": brick}
    )


@pytest.fixture
def brick_processes():
    """The processes of each brick that a step started: {name: pids}."""

    return {}


@pytest.fixture
def other_switch(desktop, tmp_path):
    """
    A vde_switch that the tests run, as another program would, for a switch
    wrapper: its control folder, path, and its process. It is in the
    runtime folder of the tests, out of that of Virtualbricks, and quits at
    the end of the scenario.
    """

    folder = tempfile.mkdtemp(dir=desktop.runtime)
    path = os.path.join(folder, "switch.ctl")
    with open(tmp_path / "other-switch.log", "wb") as log:
        # it quits at the end of its input
        process = subprocess.Popen(
            ["vde_switch", "-s", path],
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=log,
        )
    try:
        harness.a11y.wait_for(
            lambda: os.path.exists(os.path.join(path, "ctl")),
            "the switch of another program listens",
        )
        yield types.SimpleNamespace(path=path, process=process)
    finally:
        process.stdin.close()
        try:
            process.wait(harness.TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        shutil.rmtree(folder, ignore_errors=True)


# A drive without a trash: a file system in memory that the system mounts,
# where the desktop makes none
NO_TRASH = "/dev/shm"


@pytest.fixture
def drive_without_trash(virtualbricks):
    """
    A folder on a drive without a trash, out of the home of Virtualbricks,
    which has its trash. It is removed once Virtualbricks has stopped:
    Virtualbricks writes in its workspace until it quits.
    """

    if not os.path.isdir(NO_TRASH):
        pytest.skip(f"no {NO_TRASH}")
    folder = tempfile.mkdtemp(prefix="vb-e2e-", dir=NO_TRASH)
    try:
        yield folder
    finally:
        virtualbricks.stop()
        shutil.rmtree(folder, ignore_errors=True)


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


@then("Virtualbricks hasn't quit")
def virtualbricks_not_quit(virtualbricks):
    """It still runs, and its main window shows."""

    status = virtualbricks.process.poll()
    assert status is None, f"Virtualbricks exited with {status}"
    virtualbricks.find("frame")


def project_path(virtualbricks):
    """The path of the file of the project, the one of the workspace."""

    files = glob.glob(
        os.path.join(virtualbricks.workspace, "*", "project.toml")
    )
    assert len(files) == 1, f"not one project: {files}"
    return files[0]


def project_file(virtualbricks):
    """The file of the project, the one of the workspace."""

    with open(project_path(virtualbricks), "rb") as file:
        return tomllib.load(file)


@then("project.toml has the bricks")
def project_bricks(virtualbricks, datatable):
    """
    The bricks of the file of the project, all of them and in order, are
    those of the table under the step: the name of each and its type.
    """

    bricks = project_file(virtualbricks).get("bricks", {})
    found = datatable[:1] + [
        [name, table["type"]] for name, table in bricks.items()
    ]
    assert found == datatable, f"project.toml has {found}, not {datatable}"


@then(words("project.toml has {name:Brick} with"))
def project_brick(virtualbricks, name, datatable):
    """
    The brick in the file of the project has the settings of the table
    under the step, a name and a value each, as TOML writes it.
    """

    brick = project_brick_of(virtualbricks, name)
    for setting, value in datatable[1:]:
        wanted = tomllib.loads(f"value = {value}")["value"]
        assert (
            brick[setting] == wanted
        ), f"{name}: {setting} is {brick[setting]!r}, not {wanted!r}"


@then(
    words("project.toml has {name:Brick} with the settings of {other:Brick}")
)
def project_same(virtualbricks, name, other):
    """The two bricks of the file of the project have the same settings."""

    brick = project_brick_of(virtualbricks, name)
    model = project_brick_of(virtualbricks, other)
    assert brick == model, f"{name} has {brick}, {other} {model}"


def project_brick_of(virtualbricks, name):
    """The table of the brick name in the file of the project."""

    bricks = project_file(virtualbricks).get("bricks", {})
    assert name in bricks, f"project.toml has no {name}"
    return bricks[name]


@then(words("the main window shows the project {name:Project}"))
def main_window(virtualbricks, name):
    """
    Its title names the project, and the workspace too when it isn't that of
    the settings.
    """

    workspace = virtualbricks.workspace
    # with ~ for the home, as Virtualbricks says it
    if workspace.startswith(virtualbricks.home + os.sep):
        workspace = "~" + workspace[len(virtualbricks.home) :]
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


# The kinds of bricks that run no program, as their rows say them: a switch
# wrapper is a switch that another program runs.
NO_PROGRAM = ("Switch wrapper",)
# What the tab Bricks says in place of its list, when there are no bricks
NO_BRICKS = "No Bricks Yet"


@when(words("I start {name:Brick}"))
def start_brick(virtualbricks, brick_processes, name):
    """
    Its button Start; then it runs, with new processes, unless it is of a
    kind that runs no program.
    """

    detail = virtualbricks.names("label", within=virtualbricks.row(name))[1]
    before = virtualbricks.children()
    virtualbricks.click("button", f"Start {name}")
    virtualbricks.find("button", f"Stop {name}")
    if detail.startswith(NO_PROGRAM):
        brick_processes[name] = set()
        return
    brick_processes[name] = virtualbricks.wait_for(
        lambda: virtualbricks.children() - before, f"a process of {name} runs"
    )


@when(words("I stop {name:Brick}"))
def stop_brick(virtualbricks, name):
    virtualbricks.click("button", f"Stop {name}")
    virtualbricks.find("button", f"Start {name}")


@when(words("I try to start {name:Brick}"))
def try_start(virtualbricks, name):
    """A click on its Start, as a user may click it also when disabled."""

    row = virtualbricks.row(name)
    virtualbricks.click("button", f"Start {name}", within=row, enabled=False)


@when(
    words(
        "I give {name:Brick} {ports:d} ports and hub mode, with the buttons"
        " of its settings"
    )
)
def give_ports(virtualbricks, name, ports):
    """
    Configure… in its menu, + or - of Ports until it says ports, Hub mode
    turned on, then OK.
    """

    change_ports(virtualbricks, name, ports)
    virtualbricks.click("button", "OK")
    virtualbricks.find("button", f"Start {name}")


@when(
    words(
        "I give {name:Brick} {ports:d} ports and hub mode in its settings,"
        " then cancel"
    )
)
def cancel_ports(virtualbricks, name, ports):
    """The same, then Cancel: the list shows again."""

    change_ports(virtualbricks, name, ports)
    virtualbricks.click("button", "Cancel")
    virtualbricks.find("button", f"Start {name}")


def change_ports(virtualbricks, name, ports):
    """
    Configure… in its menu, + or - of Ports until it says ports, and Hub
    mode turned on.
    """

    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Configure…")
    spin = virtualbricks.enabled("spin button", "Ports")
    now = int(harness.a11y.position(spin)[0])
    virtualbricks.spin("Ports", ports - now)
    hub = virtualbricks.enabled("toggle button", "Hub mode")
    if not harness.a11y.checked(hub):
        virtualbricks.click("toggle button", "Hub mode")
    virtualbricks.wait_for(
        lambda: harness.a11y.checked(hub), "Hub mode is turned on"
    )


@when(words("I duplicate {name:Brick} from its menu"))
def duplicate(virtualbricks, name):
    """Duplicate, in its menu; then the list has one more brick."""

    before = len(brick_rows(virtualbricks))
    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Duplicate")
    virtualbricks.wait_for(
        lambda: len(brick_rows(virtualbricks)) == before + 1,
        "the list has one more brick",
    )


@when(words("I delete {name:Brick} from its menu, and confirm"))
def delete(virtualbricks, name):
    """Delete…, in its menu, then Yes to the question, which names it."""

    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Delete…")
    dialog = virtualbricks.find("dialog")
    # then its type, as Virtualbricks names it inside
    question = f"Do you really want to delete {name} ("
    virtualbricks.wait_for(
        lambda: any(
            label.startswith(question)
            for label in virtualbricks.names("label", within=dialog)
        ),
        f"the dialog asks to delete {name}",
    )
    virtualbricks.click("button", "Yes", within=dialog)
    virtualbricks.gone("dialog")


@when(words("I give {name:Brick} the control folder of that switch"))
def give_folder(virtualbricks, other_switch, name):
    """
    Configure… in its menu, the folder of the switch of another program
    typed in Control folder, then OK; its row says the folder.
    """

    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Configure…")
    virtualbricks.type(other_switch.path, "text", "Control folder")
    virtualbricks.click("button", "OK")
    row = virtualbricks.row(name)
    detail = f"Switch wrapper · {other_switch.path}"
    virtualbricks.find("label", detail, within=row)


@when("I start all the bricks")
def start_all(virtualbricks, brick_processes):
    """
    Start All, over the list; then each brick whose row said Stopped, as
    those that can start, runs with the process its row tells, and Start
    All started no other.
    """

    names = [
        row[0] for row in brick_rows(virtualbricks) if row[-1] == "Stopped"
    ]
    before = virtualbricks.children()
    virtualbricks.click("button", "Start All")
    for name in names:
        virtualbricks.find("button", f"Stop {name}")
        brick_processes[name] = {process(virtualbricks, name)}
    pids = set().union(*(brick_processes[name] for name in names))
    try:
        virtualbricks.wait_for(
            lambda: virtualbricks.children() - before == pids,
            "Start All started the processes of the bricks, and no other",
        )
    except AssertionError:
        raise AssertionError(
            f"Start All started {virtualbricks.children() - before}, not"
            f" {pids}, the processes of {names}"
        ) from None


@when("I stop all the bricks")
def stop_all(virtualbricks):
    """Stop All, over the list; then each brick that ran can start."""

    names = [
        row[0] for row in brick_rows(virtualbricks) if row[-1] == "Running"
    ]
    virtualbricks.click("button", "Stop All")
    for name in names:
        virtualbricks.find("button", f"Start {name}")


@when("I show only the running bricks")
def only_running(virtualbricks):
    """Running, of the switch over the list; then it is on."""

    show_bricks(virtualbricks, "Running")


@when("I show all the bricks")
def all_bricks(virtualbricks):
    """All, of the switch over the list; then it is on."""

    show_bricks(virtualbricks, "All")


def show_bricks(virtualbricks, which):
    """A button of the switch over the list of bricks; then it is on."""

    tab = virtualbricks.find("page tab", "Bricks")
    button = virtualbricks.click("radio button", which, within=tab)
    virtualbricks.wait_for(
        lambda: harness.a11y.checked(button), f"{which} is on"
    )


def process(virtualbricks, name):
    """
    The process of the running brick name, as its row tells: the tooltip
    of its state, Process PID, which the screen readers read too.
    """

    row = virtualbricks.row(name)
    virtualbricks.find("label", "Running", within=row)
    state = state_of(virtualbricks, name)
    words = virtualbricks.wait_for(
        lambda: state.get_description(), f"the row of {name} tells its process"
    )
    return int(words.removeprefix("Process "))


def state_of(virtualbricks, name):
    """
    The state of the brick in its row: its words, after a dot or a warning
    sign, whose tooltip says more, as the screen readers read it.
    """

    row = virtualbricks.row(name)
    words = virtualbricks.names("label", within=row)[-1]
    return virtualbricks.find("label", words, within=row).get_parent()


@then(words("{name:Brick} is running"))
@then(words("{name:Brick} is still running"))
def brick_running(virtualbricks, brick_processes, name):
    """Its row says so, and the processes of its start still run."""

    row = virtualbricks.row(name)
    virtualbricks.find("label", "Running", within=row)
    virtualbricks.find("button", f"Stop {name}", within=row)
    pids = brick_processes.get(name, set())
    assert pids <= virtualbricks.children(), f"the processes of {name} quit"


def brick_rows(virtualbricks):
    """
    The rows of the list of bricks, all of them and in order: each the
    name of a brick, its detail and its state. No rows when the tab says
    that there are no bricks, in place of the list.
    """

    return tab_rows(virtualbricks, "Bricks", NO_BRICKS)


def tab_rows(virtualbricks, title, empty):
    """
    The rows of the list of the tab title, all of them and in order, each
    the names of its labels; no rows when the tab says empty in place of
    the list.
    """

    tab = virtualbricks.find("page tab", title)
    shown = virtualbricks.wait_for(
        lambda: virtualbricks.shows("scroll pane", within=tab)
        or virtualbricks.shows("label", empty, within=tab),
        f"the list of the tab {title} shows, or {empty!r}",
    )
    if shown.get_role_name() == "label":
        return []
    return virtualbricks.rows(shown)


@then(words("{name:Brick} runs with {ports:d} ports, as a hub"))
def runs_as_hub(virtualbricks, brick_processes, name, ports):
    """It runs, and its vde_switch has -n ports and -x, a hub."""

    brick_running(virtualbricks, brick_processes, name)
    for pid in brick_processes[name]:
        words = virtualbricks.command_line(pid)
        if "-n" in words:
            assert words[words.index("-n") + 1] == str(ports), words
            assert "-x" in words, f"not a hub: {words}"
            return
    raise AssertionError(f"no vde_switch of {name} runs")


@then("the list of bricks has")
def bricks_listed(virtualbricks, datatable):
    """
    Its rows, all of them and in order, once they are those of the table
    under the step, whose first line has the titles of the columns: each
    row has the name of the brick, its detail and its state.
    """

    def rows():
        return datatable[:1] + brick_rows(virtualbricks)

    try:
        virtualbricks.wait_for(
            lambda: rows() == datatable,
            "the list of bricks has the rows of the table",
        )
    except AssertionError:
        raise AssertionError(
            f"the list of bricks has {rows()}, not {datatable}"
        ) from None


@then(words("the list of bricks shows only {name:Brick}, with its process"))
def only_listed(virtualbricks, brick_processes, name):
    """
    The list has its row alone, once it says Running and, in place of its
    summary, a process of its start, which still runs.
    """

    pids = brick_processes[name]

    def listed():
        rows = brick_rows(virtualbricks)
        if len(rows) != 1 or rows[0][0] != name or rows[0][2] != "Running":
            return None
        # the last part of its detail
        process = rows[0][1].rpartition(" · ")[2]
        for pid in pids:
            if process == f"process {pid}":
                return pid
        return None

    try:
        pid = virtualbricks.wait_for(
            listed, f"the list of bricks shows only {name}, with its process"
        )
    except AssertionError:
        raise AssertionError(
            f"the list of bricks has {brick_rows(virtualbricks)}, not only"
            f" {name} with one of {pids}"
        ) from None
    assert pid in virtualbricks.children(), f"the process {pid} quit"


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


@then("no brick runs")
def no_brick_runs(virtualbricks, brick_processes):
    """
    No row of the list says Running, and no process of a brick runs:
    neither those that the steps started nor any with a socket of the
    tests; Virtualbricks runs no program.
    """

    virtualbricks.wait_for(
        lambda: all(row[-1] != "Running" for row in brick_rows(virtualbricks)),
        "no row of the list says Running",
    )
    pids = set().union(*brick_processes.values())
    virtualbricks.wait_for(
        lambda: not pids & virtualbricks.children()
        and not virtualbricks.bricks()
        and not virtualbricks.children(),
        "the processes of the bricks quit",
    )


@then(words("{name:Brick} is not configured"))
def not_configured(virtualbricks, name):
    """
    Its row says so, its Start is disabled, and no process has its
    sockets.
    """

    row = virtualbricks.row(name)
    virtualbricks.find("label", "Not configured", within=row)
    virtualbricks.disabled("button", f"Start {name}", within=row)
    assert not virtualbricks.bricks(
        name
    ), f"a process has the sockets of {name}"


@then(words('{name:Brick} can\'t start: "{why}"'))
def cant_start(virtualbricks, name, why):
    """
    Its Start is disabled, and the state in its row says why, in its
    tooltip, which the screen readers read.
    """

    row = virtualbricks.row(name)
    virtualbricks.disabled("button", f"Start {name}", within=row)
    state = state_of(virtualbricks, name)
    try:
        virtualbricks.wait_for(
            lambda: state.get_description() == why,
            f"the row of {name} says why it can't start",
        )
    except AssertionError:
        raise AssertionError(
            f"the row of {name} says {state.get_description()!r}, not {why!r}"
        ) from None


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


# Projects

PROJECTS_WINDOW = "Projects"


@given("the workspace is on a drive without a trash")
def workspace_without_trash(virtualbricks, drive_without_trash):
    """The workspace of Virtualbricks in a folder of that drive."""

    assert virtualbricks.process is None, "Virtualbricks runs already"
    virtualbricks.workspace = os.path.join(drive_without_trash, "workspace")
    os.makedirs(virtualbricks.workspace)


@when("I open the Projects window")
def open_projects(virtualbricks):
    """Projects…, in the menu Projects."""

    virtualbricks.choose("Projects…", "Projects")
    virtualbricks.find("frame", PROJECTS_WINDOW)


@when(words("I make a new project with the name it suggests, {name:Project}"))
def new_project(virtualbricks, name):
    """
    New…, in the Projects window: the name it suggests is name; then Create,
    and the dialog closes.
    """

    window = virtualbricks.find("frame", PROJECTS_WINDOW)
    virtualbricks.click("button", "New…", within=window)
    dialog = virtualbricks.find("dialog", "New Project")
    suggests(virtualbricks, dialog, "Name", name)
    virtualbricks.click("button", "Create", within=dialog)
    virtualbricks.gone("dialog", "New Project")


@when(
    words(
        "I duplicate the project {name:Project} with the name it suggests,"
        " {copy:Project}"
    )
)
def duplicate_project(virtualbricks, name, copy):
    """
    In the Projects window, its row, then Duplicate… in its details: the
    name it suggests is copy; then Duplicate, with Open the copy as it is,
    and the dialog closes.
    """

    details = select_project(virtualbricks, name)
    virtualbricks.click("button", "Duplicate…", within=details)
    dialog = virtualbricks.find("dialog", "Duplicate Project")
    suggests(virtualbricks, dialog, "Name of the copy", copy)
    virtualbricks.click("button", "Duplicate", within=dialog)
    virtualbricks.gone("dialog", "Duplicate Project")


def suggests(virtualbricks, dialog, field, name):
    """The field of the name, in the dialog of a project, says name."""

    entry = virtualbricks.find("text", field, within=dialog)
    try:
        virtualbricks.wait_for(
            lambda: harness.a11y.text(entry) == name,
            f"the dialog suggests {name}",
        )
    except AssertionError:
        raise AssertionError(
            f"the dialog suggests {harness.a11y.text(entry)!r}, not {name!r}"
        ) from None


@when(words("I open the project {name:Project}"))
def open_project(virtualbricks, name):
    """
    In the Projects window, its row, then Open in its details; the window
    closes.
    """

    click_open(virtualbricks, name)
    virtualbricks.gone("frame", PROJECTS_WINDOW)


@when(words("I try to open the project {name:Project}"))
def try_open_project(virtualbricks, name):
    """The same, without waiting for the window to close."""

    click_open(virtualbricks, name)


def click_open(virtualbricks, name):
    """
    In the Projects window, the row of the project name, then Open in its
    details.
    """

    details = select_project(virtualbricks, name)
    virtualbricks.click("button", "Open", within=details)


def select_project(virtualbricks, name):
    """
    In the Projects window, the row of the project name: its details, once
    they show its folder.
    """

    window = virtualbricks.find("frame", PROJECTS_WINDOW)
    item = virtualbricks.wait_for(
        lambda: project_row(window, name), f"the row of {name} shows"
    )
    virtualbricks.click("label", name, within=item)
    path = os.path.join(virtualbricks.workspace, name)
    return virtualbricks.find("label", path, within=window).get_parent()


def project_row(window, name):
    """The row of the project name in the Projects window, if it shows."""

    for item in harness.a11y.find_all(window, "list item"):
        if harness.a11y.find(item, "label", name) is not None:
            return item
    return None


@when(words("I remove the project {name:Project}, and move it to the trash"))
def trash_project(virtualbricks, name):
    """
    In the Projects window, its row, then Remove… in the menu of its
    details; the question, which names it, says its folder goes to the
    trash: Move to Trash, and the question closes.
    """

    question = ask_remove(virtualbricks, name)
    says(virtualbricks, question, " to the trash, where you can restore it.")
    virtualbricks.click("button", "Move to Trash", within=question)
    virtualbricks.gone("alert", QUESTION)


@when(
    words(
        "I remove the project {name:Project}, which can't go to the trash,"
        " and delete it permanently"
    )
)
def delete_project(virtualbricks, name):
    """
    The same, where the question has no Move to Trash, and says the drive
    of the workspace has none: Delete Permanently.
    """

    question = ask_remove(virtualbricks, name)
    says(virtualbricks, question, " the drive of the workspace has no trash.")
    assert (
        virtualbricks.shows("button", "Move to Trash", within=question) is None
    ), "the question offers the trash"
    virtualbricks.click("button", "Delete Permanently", within=question)
    virtualbricks.gone("alert", QUESTION)


# A dialog that asks, as the screen readers name it
QUESTION = "Question"


def ask_remove(virtualbricks, name):
    """
    In the Projects window, the row of the project name, then Remove… in the
    menu of its details: the question, once it names the project.
    """

    details = select_project(virtualbricks, name)
    virtualbricks.click("toggle button", "Menu", within=details)
    virtualbricks.click("button", "Remove…")
    question = virtualbricks.find("alert", QUESTION)
    virtualbricks.find("label", f"Remove {name}?", within=question)
    return question


def says(virtualbricks, dialog, text):
    """A label of the dialog has text, once it shows."""

    virtualbricks.wait_for(
        lambda: any(
            text in label
            for label in virtualbricks.names("label", within=dialog)
        ),
        f"the dialog says {text!r}",
    )


@then(words("the Projects window doesn't list {name:Project}"))
def projects_not_listed(virtualbricks, name):
    window = virtualbricks.find("frame", PROJECTS_WINDOW)
    virtualbricks.wait_for(
        lambda: project_row(window, name) is None,
        f"the Projects window doesn't list {name}",
    )


@then(words("the folder of {name:Project} is in the trash"))
def project_in_trash(virtualbricks, name):
    """
    The workspace has no folder name any more, and the trash of the home
    has it: in its folder info, a .trashinfo that says where it was, and in
    files, the folder, with its project.toml.
    """

    path = os.path.join(virtualbricks.workspace, name)
    virtualbricks.wait_for(
        lambda: not os.path.exists(path), f"the workspace has no {name}"
    )
    trash = os.path.join(virtualbricks.home, TRASH)
    trashed = trashed_as(trash, path)
    assert trashed is not None, f"the trash has no {path}"
    toml = os.path.join(trash, "files", trashed, "project.toml")
    assert os.path.isfile(toml), f"the trash has {path} without project.toml"


@then(words("the folder of {name:Project} is deleted, and in no trash"))
def project_deleted(virtualbricks, name):
    """
    The workspace has no folder name any more, and no trash has it: neither
    that of the home, nor those of the drive of the workspace, .Trash/UID
    and .Trash-UID at its top.
    """

    path = os.path.join(virtualbricks.workspace, name)
    virtualbricks.wait_for(
        lambda: not os.path.exists(path), f"the workspace has no {name}"
    )
    top = virtualbricks.workspace
    while not os.path.ismount(top):
        top = os.path.dirname(top)
    uid = str(os.getuid())
    for trash, drive in (
        (os.path.join(virtualbricks.home, TRASH), None),
        (os.path.join(top, ".Trash", uid), top),
        (os.path.join(top, f".Trash-{uid}"), top),
    ):
        assert trashed_as(trash, path, drive) is None, f"{trash} has {path}"


# The trash of the home, in the data folder of Virtualbricks
TRASH = os.path.join(".local", "share", "Trash")


def trashed_as(trash, path, drive=None):
    """
    The name in the trash of what was at path, by the .trashinfo files of
    its folder info; None if it isn't there. In the trash of a drive, the
    path is relative to the top of the drive.
    """

    info = os.path.join(trash, "info")
    if not os.path.isdir(info):
        return None
    for file in os.listdir(info):
        name, extension = os.path.splitext(file)
        if extension != ".trashinfo":
            continue
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(os.path.join(info, file))
        was = urllib.parse.unquote(parser["Trash Info"]["Path"])
        if os.path.join(drive or "/", was) == path:
            return name
    return None


IMPORT_WINDOW = "Import Project"


@when(
    words(
        "I import the archive {archive} of my home folder with the name it"
        " suggests, {name:Project}"
    )
)
def import_archive(virtualbricks, archive, name):
    """
    Import…, in the menu Projects; in the window, the button of the file,
    then Home and the archive in the file chooser, and Open; the name it
    suggests is name; then Import, and the window says how it ended.
    """

    virtualbricks.choose("Import…", "Projects")
    window = virtualbricks.find("frame", IMPORT_WINDOW)
    # the button of the file names it: none yet
    virtualbricks.click("button", "(None)", within=window)
    chooser = virtualbricks.find("file chooser", "Choose an archive")
    virtualbricks.click("label", "Home", within=chooser)
    virtualbricks.click("table cell", archive, within=chooser)
    virtualbricks.click("button", "Open", within=chooser)
    virtualbricks.gone("file chooser", "Choose an archive")
    suggests(virtualbricks, window, "Name", name)
    virtualbricks.click("button", "Import", within=window)
    # in place of Import and Cancel, once it is imported, or failed
    virtualbricks.find("button", "Close", within=window)


@then(words('the Import Project window says "{text}"'))
def import_window_says(virtualbricks, text):
    window = virtualbricks.find("frame", IMPORT_WINDOW)
    virtualbricks.find("label", text, within=window)


@when("I close the Import Project window")
def close_import(virtualbricks):
    window = virtualbricks.find("frame", IMPORT_WINDOW)
    virtualbricks.click("button", "Close", within=window)
    virtualbricks.gone("frame", IMPORT_WINDOW)


@then(words('the Projects window says "{text}"'))
def projects_window_says(virtualbricks, text):
    window = virtualbricks.find("frame", PROJECTS_WINDOW)
    virtualbricks.find("label", text, within=window)


@then(words("the folder of {name:Project} has project.toml"))
def project_toml(virtualbricks, name):
    """
    The folder of the project in the workspace has the file of a project of
    this version, which TOML reads.
    """

    path = os.path.join(virtualbricks.workspace, name, "project.toml")
    assert os.path.isfile(path), f"{path} is missing"
    with open(path, "rb") as file:
        data = tomllib.load(file)
    assert "format" in data, f"{path} has no format: {data}"


@then(
    words("the folder of {copy:Project} is a copy of that of {name:Project}")
)
def project_copy(virtualbricks, copy, name):
    """
    The two folders of the workspace have the same files, with the same
    bytes, and the copy has its project.toml.
    """

    def files(project):
        folder = os.path.join(virtualbricks.workspace, project)
        found = {}
        for root, _, names in os.walk(folder):
            for file in names:
                path = os.path.join(root, file)
                with open(path, "rb") as data:
                    found[os.path.relpath(path, folder)] = data.read()
        return found

    project_toml(virtualbricks, copy)
    try:
        virtualbricks.wait_for(
            lambda: files(copy) == files(name),
            f"the folder of {copy} is a copy of that of {name}",
        )
    except AssertionError:
        ours, theirs = files(copy), files(name)
        differ = sorted(
            path
            for path in ours.keys() | theirs.keys()
            if ours.get(path) != theirs.get(path)
        )
        raise AssertionError(
            f"the folders of {copy} and {name} differ in {differ}"
        ) from None


# Disk images

# The units of the sizes of the disks, as Virtualbricks counts them
UNITS = {"MB": 1000**2, "GB": 1000**3}
# The folder of the images, in the workspace
IMAGE_FOLDER = "vimages"
ADD_IMAGE = "Add an Existing Image"
CHOOSE_IMAGE = "Choose a Disk Image"
# What the tab Images says in place of its list, when there are no images
NO_IMAGES = "No Images Yet"
# Between the parts of the detail of a row
SEPARATOR = " · "


@given(
    words("the empty disk image {file} of {size:d} {unit}, in my home folder")
)
def disk_image(virtualbricks, file, size, unit):
    """
    In the home, an empty disk of size MB or GB, made with qemu-img create,
    in the format of the extension of file: qcow2, or raw.
    """

    path = os.path.join(virtualbricks.home, file)
    fmt = os.path.splitext(file)[1].removeprefix(".")
    subprocess.run(
        ["qemu-img", "create", "-q", "-f", fmt, path, str(size * UNITS[unit])],
        check=True,
    )


@when(
    words(
        "I add an existing image, {file} of my home folder, with the name it"
        " suggests, {name:Image}"
    )
)
def add_image(virtualbricks, file, name):
    """
    The tab Images, Add Image, then Existing Image…; in the dialog, the
    button of the file, then Home and the file in the file chooser, and
    Open; the name it suggests is name; then Add, with Copy it to the image
    folder as it is, and the dialog closes.
    """

    tab = virtualbricks.click("page tab", "Images")
    virtualbricks.click("button", "Add Image", within=tab)
    virtualbricks.click("button", "Existing Image…")
    dialog = virtualbricks.find("dialog", ADD_IMAGE)
    # the button of the file names it: none yet
    virtualbricks.click("button", "(None)", within=dialog)
    chooser = virtualbricks.find("file chooser", CHOOSE_IMAGE)
    virtualbricks.click("label", "Home", within=chooser)
    virtualbricks.click("table cell", file, within=chooser)
    virtualbricks.click("button", "Open", within=chooser)
    virtualbricks.gone("file chooser", CHOOSE_IMAGE)
    suggests(virtualbricks, dialog, "Name", name)
    # it shows once the file is read, a disk image out of the workspace
    copy = virtualbricks.find(
        "radio button", "Copy it to the image folder", within=dialog
    )
    assert harness.a11y.checked(copy), "the file is used where it is"
    virtualbricks.click("button", "Add", within=dialog)
    virtualbricks.gone("dialog", ADD_IMAGE)


def image_rows(virtualbricks):
    """
    The rows of the list of images, all of them and in order: each the
    name of an image, its detail and its state. The detail is without the
    space its file takes, "… on disk", which depends on the file system.
    """

    def detail(words):
        parts = words.split(SEPARATOR)
        return SEPARATOR.join(
            part for part in parts if not part.endswith(" on disk")
        )

    return [
        [row[0], detail(row[1]), *row[2:]]
        for row in tab_rows(virtualbricks, "Images", NO_IMAGES)
    ]


@then("the list of images has")
def images_listed(virtualbricks, datatable):
    """
    Its rows, all of them and in order, once they are those of the table
    under the step, whose first line has the titles of the columns: each
    row has the name of the image, its detail, without the space its file
    takes, and its state.
    """

    def rows():
        return datatable[:1] + image_rows(virtualbricks)

    try:
        virtualbricks.wait_for(
            lambda: rows() == datatable,
            "the list of images has the rows of the table",
        )
    except AssertionError:
        raise AssertionError(
            f"the list of images has {rows()}, not {datatable}"
        ) from None


@then(words("the image folder has {file}, a copy of that of my home folder"))
def image_copied(virtualbricks, file):
    """
    The image folder of the workspace has the file, with the bytes of that
    of the home, which stays.
    """

    original = os.path.join(virtualbricks.home, file)
    copy = os.path.join(virtualbricks.workspace, IMAGE_FOLDER, file)
    assert os.path.isfile(original), f"{original} is gone"
    assert os.path.isfile(copy), f"{copy} is missing"
    with open(original, "rb") as theirs, open(copy, "rb") as ours:
        assert ours.read() == theirs.read(), f"{copy} differs from {original}"


@then(
    words(
        "project.toml has the image {name:Image}, of {file} in the image"
        " folder"
    )
)
def project_image(virtualbricks, name, file):
    """
    The image in the file of the project has the file of the image folder
    of the workspace: its path, or one relative to the folder of the
    project.
    """

    path = project_path(virtualbricks)
    images = project_file(virtualbricks).get("images", {})
    assert name in images, f"project.toml has no image {name}: {images}"
    found = os.path.join(os.path.dirname(path), images[name]["path"])
    wanted = os.path.join(virtualbricks.workspace, IMAGE_FOLDER, file)
    assert os.path.normpath(found) == wanted, f"{name} is of {found}"


# A program that fails, and what Virtualbricks says of it


@given(words('a vde_switch that writes "{text}" and exits with {status:d}'))
def failing_switch(virtualbricks, text, status):
    """
    A script of its own in place of vde_switch, in the folder of the VDE
    programs of the project that Virtualbricks opens at its first start,
    new_project: it writes text on its standard error, and exits.
    """

    assert virtualbricks.process is None, "Virtualbricks runs already"
    folder = os.path.join(virtualbricks.home, "vde")
    os.makedirs(folder)
    program = os.path.join(folder, "vde_switch")
    with open(program, "w") as file:
        file.write(
            f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(text)} >&2\n"
            f"exit {status}\n"
        )
    os.chmod(program, 0o755)
    project = os.path.join(virtualbricks.workspace, "new_project")
    os.makedirs(project)
    with open(os.path.join(project, "project.toml"), "w") as file:
        file.write(f"format = 2\n\n[settings]\nvde_path = {folder!r}\n")


@then(words('an error says "{text}"'))
def error_says(virtualbricks, text):
    alert = virtualbricks.find("alert", "Error")
    virtualbricks.find("label", text, within=alert)


@when("I close the error")
def close_error(virtualbricks):
    alert = virtualbricks.find("alert", "Error")
    virtualbricks.click("button", "Close", within=alert)
    virtualbricks.gone("alert", "Error")


@when("I open the messages window")
def open_messages(virtualbricks):
    """Logs, in the menu File."""

    virtualbricks.choose("Logs", "File")
    virtualbricks.find("frame", "Logs")


@then(words('the messages window has the output of {name:Brick}: "{text}"'))
def messages_output(virtualbricks, name, text):
    """
    A line of its messages comes from the brick, and has text, as its
    program wrote it on its standard output, or on its standard error, after
    2>.
    """

    window = virtualbricks.find("frame", "Logs")
    pane = virtualbricks.find("scroll pane", within=window)
    view = virtualbricks.find("text", within=pane)

    def output():
        for line in harness.a11y.text(view).splitlines():
            fields = [field for field in line.split("\t") if field]
            if name in fields and (text in fields or f"2> {text}" in fields):
                return line
        return None

    virtualbricks.wait_for(output, f"the output of {name} is in the window")


# A switch that another program runs: the fixture other_switch


@given("a switch that another program runs")
def other_switch_runs(other_switch):
    """The tests run it, in other_switch."""


@then("the switch that another program runs still runs")
def other_switch_still_runs(other_switch):
    assert other_switch.process.poll() is None, "it quit"
    control = os.path.join(other_switch.path, "ctl")
    assert os.path.exists(control), f"{control} is gone"


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
    words(
        "the archive {name:Project}.vbp of Virtualbricks 2.1, in my home folder"
    )
)
def old_archive(virtualbricks, name):
    """
    In the home, the archive of projects/NAME as 2.1 exported it: its
    .project, without images, in a tar compressed with gzip, as tar cfz did.
    """

    path = os.path.join(virtualbricks.home, f"{name}.vbp")
    with tarfile.open(path, "w:gz") as archive:
        archive.add(os.path.join(PROJECTS, name, ".project"), ".project")


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
