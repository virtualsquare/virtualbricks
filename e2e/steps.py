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
import json
import os
import re
import shlex
import shutil
import socket
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

import cairo
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
def picture_scroll():
    """
    Where the picture of the lab was scrolled to before a drag, {"before":
    the value of its horizontal scroll bar}.
    """

    return {}


@pytest.fixture
def old_files():
    """
    The files of Virtualbricks 2.1 that a step wrote in the workspace, as
    they were: {path in the workspace: bytes}.
    """

    return {}


@pytest.fixture
def migrated_before():
    """
    The projects that a migration closed while it ran had migrated:
    {name: the time and the bytes of its project.toml}.
    """

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


@given(words("Virtualbricks is running with {options}"))
def running_with(virtualbricks, request, options):
    """
    Started with the options, as the shell splits them, and its main window
    shows; with --listen alone, it listens too. With --connect, the windows
    of the other Virtualbricks, which runs the bricks.
    """

    options = shlex.split(options)
    if "--connect" in options:
        virtualbricks.lab = request.getfixturevalue("other_virtualbricks")
        assert virtualbricks.lab.process is not None, "no other one runs"
    virtualbricks.start(*options)


@given(words("another Virtualbricks runs with {options}"))
def other_runs(other_virtualbricks, options):
    """
    Another Virtualbricks of mine, in the same workspace, started with the
    options: its main window shows, or, with --no-gui, it listens on the
    socket of --listen alone.
    """

    other_virtualbricks.start(*shlex.split(options))


@when(words("I start another Virtualbricks with {options}"))
def start_other(other_virtualbricks, options):
    """The same, without waiting for it: it may exit."""

    other_virtualbricks.launch(*shlex.split(options))


@then(words('the other Virtualbricks exits with {status:d}, saying "{text}"'))
def other_exits(other_virtualbricks, status, text):
    """It exits with status, and its output has text."""

    try:
        code = other_virtualbricks.process.wait(harness.QUIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise AssertionError(
            f"the other Virtualbricks still runs after {harness.QUIT_TIMEOUT} s"
        ) from None
    with open(other_virtualbricks.log, errors="replace") as file:
        output = file.read()
    assert code == status, f"it exited with {code}: {output}"
    assert text in output, f"it said {output!r}"


@then("the other Virtualbricks names the process of Virtualbricks")
def other_names(virtualbricks, other_virtualbricks):
    """Its output says the process that holds what it needs, by its pid."""

    with open(other_virtualbricks.log, errors="replace") as file:
        output = file.read()
    # then the user, if known
    held = rf"\bHeld by process {virtualbricks.process.pid}\b"
    assert re.search(held, output), f"it said {output!r}"


@when(words("I run virtualbricks --command {command}"))
def run_command(virtualbricks, command):
    """
    virtualbricks --command and the words of the command, as the shell
    splits them, in the workspace of Virtualbricks; it exits with 0.
    """

    done = virtualbricks.run("--command", *shlex.split(command))
    assert done.returncode == 0, (
        f"virtualbricks --command {command} exited with {done.returncode}:"
        f" {done.stdout}{done.stderr}"
    )


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
    """
    It exits with 0, and no brick runs any more; the windows of another
    leave the bricks there.
    """

    try:
        status = virtualbricks.process.wait(harness.QUIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise AssertionError(
            f"Virtualbricks still runs after {harness.QUIT_TIMEOUT} s"
        )
    assert status == 0, f"Virtualbricks exited with {status}"
    if virtualbricks.lab is virtualbricks:
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

    has_bricks(project_file(virtualbricks), datatable, "project.toml")


def has_bricks(project, datatable, where):
    """
    The bricks of project, the data of a project.toml, are those of the
    table: the name of each and its type.
    """

    bricks = project.get("bricks", {})
    found = datatable[:1] + [
        [name, table["type"]] for name, table in bricks.items()
    ]
    assert found == datatable, f"{where} has {found}, not {datatable}"


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


@then(words("the main window shows the project {name:Project} on {where}"))
def main_window_on(virtualbricks, name, where):
    """
    The windows of another Virtualbricks: their title names the project and
    where it runs, and the workspace too, with its path there, when it isn't
    that of the settings.
    """

    workspace = virtualbricks.workspace
    titles = (
        f"Virtualbricks (project: {name} on {where})",
        f"Virtualbricks (project: {name}, workspace: {workspace} on {where})",
    )
    virtualbricks.wait_for(
        lambda: any(virtualbricks.shows("frame", title) for title in titles),
        f"the main window shows the project {name} on {where}",
    )


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


@when(
    words(
        "I give {name:Brick} {ports:d} ports and hub mode in its settings,"
        " then press Escape"
    )
)
def escape_ports(virtualbricks, name, ports):
    """The same, then Escape: the list shows again."""

    change_ports(virtualbricks, name, ports)
    virtualbricks.key("Escape", virtualbricks.find("frame"))
    virtualbricks.find("button", f"Start {name}")


def change_ports(virtualbricks, name, ports):
    """
    Configure… in its menu, + or - of Ports until it says ports, and Hub
    mode turned on.
    """

    configure(virtualbricks, name)
    spin = virtualbricks.enabled("spin button", "Ports")
    now = int(harness.a11y.position(spin)[0])
    virtualbricks.spin("Ports", ports - now)
    hub = virtualbricks.enabled("toggle button", "Hub mode")
    if not harness.a11y.checked(hub):
        virtualbricks.click("toggle button", "Hub mode")
    virtualbricks.wait_for(
        lambda: harness.a11y.checked(hub), "Hub mode is turned on"
    )


def configure(virtualbricks, name):
    """Configure…, in the menu of the brick: its settings show."""

    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Configure…")


def settings_page(virtualbricks, page):
    """The page of the settings of a brick, in the list at their left."""

    virtualbricks.click("label", page, within=virtualbricks.row(page))


@when(
    words(
        'I turn {state} "{setting}" in the settings of {name:Brick}, on its'
        " page {page}"
    )
)
def turn_brick_setting(virtualbricks, state, setting, name, page):
    """
    Configure… in its menu; on the page of its settings, the switch of the
    setting, which is the other way, turned on or off; then OK.
    """

    on = turned(state)
    configure(virtualbricks, name)
    settings_page(virtualbricks, page)
    switch = virtualbricks.enabled("toggle button", setting)
    assert harness.a11y.checked(switch) != on, f"{setting} is already {state}"
    virtualbricks.click("toggle button", setting)
    virtualbricks.wait_for(
        lambda: harness.a11y.checked(switch) == on, f"{setting} is {state}"
    )
    virtualbricks.click("button", "OK")
    virtualbricks.find("button", f"Start {name}")


@when(
    words(
        'I choose "{choice}" for "{setting}" in the settings of {name:Brick},'
        " on its page {page}"
    )
)
def choose_brick_setting(virtualbricks, choice, setting, name, page):
    """
    Configure… in its menu; on the page of its settings, the list of the
    setting, which shows another choice, then the choice; then OK.
    """

    configure(virtualbricks, name)
    settings_page(virtualbricks, page)
    row = virtualbricks.row(setting)
    # named after what it shows
    shown = virtualbricks.enabled("combo box", within=row).get_name()
    assert shown != choice, f"{setting} is already {choice}"
    choose_in_combo(virtualbricks, row, shown, choice)
    virtualbricks.click("button", "OK")
    virtualbricks.find("button", f"Start {name}")


@when(words("I terminate {name:Brick}, from its menu"))
def terminate(virtualbricks, brick_processes, name):
    """
    In its menu, Process and its number, then Terminate; then it can start
    again, and the processes of its start have quit.
    """

    process_item(virtualbricks, name, "Terminate")
    virtualbricks.find("button", f"Start {name}")
    pids = brick_processes.get(name, set())
    virtualbricks.wait_for(
        lambda: not pids & virtualbricks.children(),
        f"the processes of {name} quit",
    )


@when(words("I pause {name:Brick}, from its menu"))
def pause(virtualbricks, name):
    """In its menu, Process and its number, then Pause: SIGSTOP."""

    process_item(virtualbricks, name, "Pause")


@when(words("I continue {name:Brick}, from its menu"))
def continue_(virtualbricks, name):
    """In its menu, Process and its number, then Continue: SIGCONT."""

    process_item(virtualbricks, name, "Continue")


def process_item(virtualbricks, name, item):
    """
    In the menu of the running brick, Process and its number, then item;
    then the menu closes.
    """

    virtualbricks.click("button", f"Menu of {name}")
    process = virtualbricks.wait_for(
        lambda: next(
            (
                button
                for button in virtualbricks.names("button")
                if button.startswith("Process ")
            ),
            None,
        ),
        f"the menu of {name} has its process",
    )
    virtualbricks.click("button", process)
    virtualbricks.click("button", item)
    virtualbricks.gone("button", item)


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
    """
    Its row says so, and the processes of its start still run: those that
    the step that started it saw, else the process its row tells, which has
    its sockets.
    """

    row = virtualbricks.row(name)
    virtualbricks.find("label", "Running", within=row)
    virtualbricks.find("button", f"Stop {name}", within=row)
    if name not in brick_processes:
        # started by none of the steps, as by --command
        pid = process(virtualbricks, name)
        assert pid in virtualbricks.bricks(name), f"{pid} isn't of {name}"
        brick_processes[name] = {pid}
    pids = brick_processes[name]
    assert pids <= virtualbricks.children(), f"the processes of {name} quit"


@then(words("{name:Brick} runs in the other Virtualbricks"))
def runs_in_other(virtualbricks, other_virtualbricks, brick_processes, name):
    """
    The processes of its start run, started by the other Virtualbricks, and
    the windows of it run none.
    """

    pids = brick_processes[name]
    lab = virtualbricks.children(other_virtualbricks.process.pid)
    assert pids and pids <= lab, f"the other runs {lab}, not {pids}"
    windows = virtualbricks.children(virtualbricks.process.pid)
    assert not windows, f"the windows run {windows}"


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

    has_rows(
        virtualbricks,
        "the list of bricks",
        lambda: brick_rows(virtualbricks),
        datatable,
    )


def has_rows(virtualbricks, what, rows, datatable):
    """
    rows(), the rows of a list, once they are those of the table, whose
    first line has the titles of the columns; what says the list.
    """

    def found():
        return datatable[:1] + rows()

    try:
        virtualbricks.wait_for(
            lambda: found() == datatable, f"{what} has the rows of the table"
        )
    except AssertionError:
        raise AssertionError(
            f"{what} has {found()}, not {datatable}"
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


@then(words("the process of {name:Brick} is paused"))
def process_paused(virtualbricks, brick_processes, name):
    """
    The processes of its start are stopped, as SIGSTOP leaves them: T in
    /proc; its row still says Running, as nothing tells it.
    """

    pids = brick_processes[name]
    assert pids, f"{name} runs no process"
    virtualbricks.wait_for(
        lambda: all(process_state(pid) == "T" for pid in pids),
        f"the processes of {name} are stopped",
    )


@then(words("the process of {name:Brick} runs again"))
def process_runs_again(virtualbricks, brick_processes, name):
    """The processes of its start run: none is stopped, none has quit."""

    pids = brick_processes[name]
    assert pids, f"{name} runs no process"
    virtualbricks.wait_for(
        lambda: all(
            process_state(pid) not in ("T", "Z", None) for pid in pids
        ),
        f"the processes of {name} run",
    )


def process_state(pid):
    """
    The state of the process pid, as /proc says it: R, S, T when stopped,
    Z once it has quit; None once it is gone.
    """

    try:
        with open(f"/proc/{pid}/stat") as file:
            stat = file.read()
    except OSError:
        return None
    # after the name, which is in brackets and may have spaces
    return stat[stat.rindex(")") + 2 :].split()[0]


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


# Virtual machines


@when(
    words("I connect {vm:Brick} to {other:Brick}, with Connect To in its menu")
)
def connect_to(virtualbricks, vm, other):
    """Connect To, in its menu, then the other brick; then the menu closes."""

    virtualbricks.click("button", f"Menu of {vm}")
    virtualbricks.click("button", "Connect To")
    virtualbricks.click("button", other)
    virtualbricks.gone("button", "Connect To")


@then(words("{vm:Brick} runs {program}, with no display"))
def runs_program(virtualbricks, brick_processes, vm, program):
    """It runs, and a process of its start is program, with -display none."""

    brick_running(virtualbricks, brick_processes, vm)
    programs = []
    for pid in brick_processes[vm]:
        words = virtualbricks.command_line(pid)
        programs.append(os.path.basename(words[0]) if words else None)
        if programs[-1] == program:
            options = list(zip(words, words[1:]))
            assert ("-display", "none") in options, f"a display: {words}"
            return
    raise AssertionError(f"{vm} runs {programs}, not {program}")


@then(words("{vm:Brick} runs with a card in the socket of {switch:Brick}"))
def card_on_switch(virtualbricks, brick_processes, vm, switch):
    """
    It runs, and its QEMU has a VDE network card whose socket is the one
    the vde_switch of switch listens on, after -s.
    """

    brick_running(virtualbricks, brick_processes, vm)
    wanted = switch_socket(virtualbricks, brick_processes, switch)
    found = []
    for pid in brick_processes[vm]:
        words = virtualbricks.command_line(pid)
        for option, value in zip(words, words[1:]):
            # vde,id=vx0,sock=PATH
            kind, _, settings = value.partition(",")
            if option == "-netdev" and kind == "vde":
                found += [
                    setting.removeprefix("sock=")
                    for setting in settings.split(",")
                    if setting.startswith("sock=")
                ]
    assert wanted in found, f"the cards of {vm} are in {found}, not {wanted}"


@then(words('the monitor of {vm:Brick} answers "{command}" with "{answer}"'))
def monitor_answers(virtualbricks, brick_processes, vm, command, answer):
    """
    The monitor of its QEMU, on the socket of its command line, answers the
    command with a line of the answer.
    """

    said = monitor(virtualbricks, brick_processes, vm, command)
    assert (
        answer in said
    ), f"the monitor of {vm} answers {said}, not {answer!r}"


# What the monitor of QEMU writes when it waits for a command
MONITOR_PROMPT = b"(qemu) "


def monitor(virtualbricks, brick_processes, vm, command):
    """
    The lines that the monitor of the QEMU of vm answers to command, on the
    socket of a -chardev that a -mon of its command line names.
    """

    path = monitor_socket(virtualbricks, brick_processes, vm)
    with socket.socket(socket.AF_UNIX) as monitor:
        # it waits for a reading, not for a time
        monitor.settimeout(harness.TIMEOUT)
        monitor.connect(path)
        read_to_prompt(monitor)
        monitor.sendall(command.encode() + b"\n")
        said = read_to_prompt(monitor)
    # the echo of the command, with the codes of a terminal, then the
    # answer, then the prompt
    return [line.strip() for line in said.split("\r\n")[1:-1]]


def monitor_socket(virtualbricks, brick_processes, vm):
    """The path of the socket of the monitor of the QEMU of vm."""

    for pid in brick_processes[vm]:
        words = virtualbricks.command_line(pid)
        options = list(zip(words, words[1:]))
        # -mon chardev=ID, and -chardev socket,id=ID,path=PATH,…
        monitors = {
            value.removeprefix("chardev=")
            for option, value in options
            if option == "-mon"
        }
        for option, value in options:
            kind, _, settings = value.partition(",")
            settings = dict(
                setting.partition("=")[::2] for setting in settings.split(",")
            )
            if (
                option == "-chardev"
                and kind == "socket"
                and settings.get("id") in monitors
                and "path" in settings
            ):
                return settings["path"]
    raise AssertionError(f"no QEMU of {vm} has a monitor on a socket")


def read_to_prompt(monitor):
    """What the monitor writes until its prompt."""

    said = b""
    while not said.endswith(MONITOR_PROMPT):
        data = monitor.recv(4096)
        assert data, f"the monitor closed, after {said!r}"
        said += data
    return said.decode(errors="replace")


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


@when("I save the project")
def save_project(virtualbricks):
    """Save, in the menu Projects."""

    virtualbricks.choose("Save", "Projects")


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

    def choose(chooser):
        virtualbricks.click("label", "Home", within=chooser)
        virtualbricks.click("table cell", archive, within=chooser)
        virtualbricks.click("button", "Open", within=chooser)

    import_with(virtualbricks, choose, name)


@when(
    words(
        "I import the archive {archive} of my home folder, typing its path,"
        " with the name it suggests, {name:Project}"
    )
)
def import_typed(virtualbricks, archive, name):
    """
    The same, where in the file chooser, once clicked, Ctrl+L shows the
    entry of its location: the path of the archive typed there, then Return
    once Open is enabled.
    """

    def choose(chooser):
        # the keys go to the window clicked last
        virtualbricks.click("table", "Files", within=chooser)
        virtualbricks.key("Control+l", chooser)
        path = os.path.join(virtualbricks.home, archive)
        virtualbricks.type(path, "text", within=chooser)
        virtualbricks.enabled("button", "Open", within=chooser)
        virtualbricks.key("Return", chooser)

    import_with(virtualbricks, choose, name)


CHOOSE_ARCHIVE = "Choose an archive"


def import_with(virtualbricks, choose, name):
    """
    Import…, in the menu Projects; in the window, the button of the file,
    then choose(chooser) in the file chooser, which closes; the name it
    suggests is name; then Import, and the window says how it ended.
    """

    virtualbricks.choose("Import…", "Projects")
    window = virtualbricks.find("frame", IMPORT_WINDOW)
    # the button of the file names it: none yet
    virtualbricks.click("button", "(None)", within=window)
    choose(virtualbricks.find("file chooser", CHOOSE_ARCHIVE))
    virtualbricks.gone("file chooser", CHOOSE_ARCHIVE)
    suggests(virtualbricks, window, "Name", name)
    virtualbricks.click("button", "Import", within=window)
    # in place of Import and Cancel, once it is imported, or failed
    virtualbricks.find("button", "Close", within=window)


EXPORT_WINDOW = "Export Project"


@when(words("I export the project to {archive} of my home folder"))
def export_project(virtualbricks, archive):
    """
    Export…, in the menu Projects, for the open project; in the window, the
    archive in the home, as it suggests; then Export, and Close once it says
    where it exported it.
    """

    virtualbricks.choose("Export…", "Projects")
    window = virtualbricks.find("frame", EXPORT_WINDOW)
    path = os.path.join(virtualbricks.home, archive)
    entry = virtualbricks.find("text", within=window)
    virtualbricks.wait_for(
        lambda: harness.a11y.text(entry) == path,
        f"the window suggests {path}",
    )
    virtualbricks.click("button", "Export", within=window)
    says(virtualbricks, window, f"Exported to {path}, ")
    virtualbricks.click("button", "Close", within=window)
    virtualbricks.gone("frame", EXPORT_WINDOW)


@then(words("the archive {archive} of my home folder has the bricks"))
def archive_bricks(virtualbricks, archive, datatable):
    """
    The project.toml of the archive, a tar, has the bricks of the table
    under the step, all of them and in order: the name of each and its type.
    """

    path = os.path.join(virtualbricks.home, archive)
    with tarfile.open(path) as tar:
        project = tomllib.load(tar.extractfile("project.toml"))
    has_bricks(project, datatable, f"the project.toml of {archive}")


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

IMAGES = "Images"
# The units of the sizes of the disks, as Virtualbricks counts them
UNITS = {"MB": 1000**2, "GB": 1000**3}
# The folder of the images, in the workspace
IMAGE_FOLDER = "vimages"
ADD_IMAGE = "Add an Existing Image"
CHOOSE_IMAGE = "Choose a Disk Image"
NEW_DISK = "New Empty Disk"
# What New Empty Disk has at first: the unit of the size, and the format
NEW_DISK_UNIT = "GB"
NEW_DISK_FORMAT = "qcow2"
REMOVE_IMAGE = "Remove Image"
FIND_FILE = "Find the File"
CHOOSE_FILE = "Choose the File"
# What the tab Images says in place of its list, when there are no images
NO_IMAGES = "No Images Yet"
# Between the parts of the detail of a row
SEPARATOR = " · "
# The fact of the details of an image that isn't of qemu-img info: when
# the file changed
CHANGED = "Changed"
# The options of QEMU that give a machine a disk, before its file
DISK_OPTIONS = ("-hda", "-hdb", "-hdc", "-hdd", "-fda", "-fdb", "-mtdblock")


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


@given(
    words(
        "the empty disk image {file} of {size:d} {unit}, in my home folder,"
        " with the snapshot {snapshot}"
    )
)
def disk_image_snapshot(virtualbricks, file, size, unit, snapshot):
    """The same, with a snapshot, made with qemu-img snapshot."""

    disk_image(virtualbricks, file, size, unit)
    path = os.path.join(virtualbricks.home, file)
    subprocess.run(["qemu-img", "snapshot", "-c", snapshot, path], check=True)


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

    add_existing(virtualbricks, file, name, copy=True)


@when(
    words(
        "I add an existing image, {file} of my home folder, used where it is,"
        " with the name it suggests, {name:Image}"
    )
)
def add_image_in_place(virtualbricks, file, name):
    """The same, with Use it where it is in place of the copy."""

    add_existing(virtualbricks, file, name, copy=False)


def add_existing(virtualbricks, file, name, copy):
    """
    Add Image, then Existing Image…, with the file of the home and the name
    it suggests; the file copied to the image folder, as the dialog has it
    at first, or used where it is.
    """

    tab = virtualbricks.click("page tab", IMAGES)
    virtualbricks.click("button", "Add Image", within=tab)
    virtualbricks.click("button", "Existing Image…")
    dialog = virtualbricks.find("dialog", ADD_IMAGE)
    choose_home_file(virtualbricks, dialog, CHOOSE_IMAGE, file)
    suggests(virtualbricks, dialog, "Name", name)
    # it shows once the file is read, a disk image out of the workspace
    copies = virtualbricks.find(
        "radio button", "Copy it to the image folder", within=dialog
    )
    assert harness.a11y.checked(copies), "the file is used where it is"
    if not copy:
        in_place = virtualbricks.click(
            "radio button", "Use it where it is", within=dialog
        )
        virtualbricks.wait_for(
            lambda: harness.a11y.checked(in_place), "Use it where it is is on"
        )
    virtualbricks.click("button", "Add", within=dialog)
    virtualbricks.gone("dialog", ADD_IMAGE)


def choose_home_file(virtualbricks, dialog, title, file):
    """
    In the dialog, the button of the file, which names none yet; then, in
    the file chooser of the title, Home, the file, and Open.
    """

    virtualbricks.click("button", "(None)", within=dialog)
    chooser = virtualbricks.find("file chooser", title)
    virtualbricks.click("label", "Home", within=chooser)
    virtualbricks.click("table cell", file, within=chooser)
    virtualbricks.click("button", "Open", within=chooser)
    virtualbricks.gone("file chooser", title)


@when(
    words(
        "I add a new empty disk, {name:Image}, of {size:d} {unit} in the"
        " format {fmt}"
    )
)
def add_new_disk(virtualbricks, name, size, unit, fmt):
    """
    The tab Images, Add Image, then New Empty Disk…; in the dialog, the
    name typed, the size typed and its unit chosen, the format chosen, in
    the image folder as it is; then Create, and the dialog closes.
    """

    tab = virtualbricks.click("page tab", IMAGES)
    virtualbricks.click("button", "Add Image", within=tab)
    virtualbricks.click("button", "New Empty Disk…")
    dialog = virtualbricks.find("dialog", NEW_DISK)
    virtualbricks.type(name, "text", "Name", within=dialog)
    virtualbricks.type(
        str(size), "spin button", "Size", within=dialog, over=True
    )
    choose_in_combo(virtualbricks, dialog, NEW_DISK_UNIT, unit)
    choose_in_combo(virtualbricks, dialog, NEW_DISK_FORMAT, fmt)
    virtualbricks.click("button", "Create", within=dialog)
    virtualbricks.gone("dialog", NEW_DISK)


def choose_in_combo(virtualbricks, within, shown, choice):
    """The combo box that shows shown, then choice in its list."""

    if shown == choice:
        return
    # named after what it shows
    combo = virtualbricks.click("combo box", shown, within=within)
    virtualbricks.click("menu item", choice, within=combo)
    virtualbricks.find("combo box", choice, within=within)


@when(words("I give {vm:Brick} the image {name:Image}, on its disk {device}"))
def give_image(virtualbricks, vm, name, device):
    """
    Configure… in its menu; on the page Disks of its settings, Add Disk and
    the device, then the image in the picker of the new disk; then OK.
    """

    configure(virtualbricks, vm)
    settings_page(virtualbricks, "Disks")
    virtualbricks.click("toggle button", "Add Disk")
    virtualbricks.click("button", device)
    disk = virtualbricks.row(device)
    # the picker, named after what it shows
    virtualbricks.click("toggle button", "No image", within=disk)
    virtualbricks.click("label", name, within=virtualbricks.row(name))
    virtualbricks.find("toggle button", name, within=disk)
    virtualbricks.click("button", "OK")
    virtualbricks.find("button", f"Start {vm}")


@when(words("I open the details of {name:Image}"))
def open_details(virtualbricks, name):
    """Details…, in its menu, in the tab Images; then they show."""

    tab = on_tab(virtualbricks, IMAGES)
    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Details…")
    entry = virtualbricks.find("text", "Name", within=tab)
    virtualbricks.wait_for(
        lambda: harness.a11y.text(entry) == name, f"the details of {name}"
    )


@when(
    words(
        "I remove the image {name:Image}, which {disks} loses, and move its"
        " file to the trash"
    )
)
def remove_to_trash(virtualbricks, name, disks):
    """
    Remove…, in its menu, in the tab Images: the dialog asks, and says
    that the disks lose it; Also move the file to the trash turned on, then
    Remove, and the dialog closes.
    """

    dialog = remove_image(virtualbricks, name, disks)
    trash = virtualbricks.wait_for(
        lambda: next(
            (
                check
                for check in harness.a11y.find_all(dialog, "check box")
                if check.get_name().startswith("Also move the file to the")
            ),
            None,
        ),
        "the dialog offers to move the file to the trash",
    )
    virtualbricks.click("check box", trash.get_name(), within=dialog)
    virtualbricks.wait_for(
        lambda: harness.a11y.checked(trash), "the file goes to the trash"
    )
    virtualbricks.click("button", "Remove", within=dialog)
    virtualbricks.gone("dialog", REMOVE_IMAGE)


@when(
    words(
        "I remove the image {name:Image}, which {disks} loses, and whose file"
        " {project:Project} uses too"
    )
)
def remove_shared(virtualbricks, name, disks, project):
    """
    The same, where the dialog says that the project uses the file too, and
    that it stays, and offers nothing for it; then Remove.
    """

    dialog = remove_image(virtualbricks, name, disks)
    stays = f"The project {project} uses the file too: it stays."
    virtualbricks.find("label", stays, within=dialog)
    checks = virtualbricks.names("check box", within=dialog)
    assert not checks, f"the dialog offers {checks}"
    virtualbricks.click("button", "Remove", within=dialog)
    virtualbricks.gone("dialog", REMOVE_IMAGE)


def remove_image(virtualbricks, name, disks):
    """
    Remove…, in the menu of the image, in the tab Images: the dialog, once
    it asks to remove it and says that the disks, as "the disk vm1 (hda)",
    lose it.
    """

    on_tab(virtualbricks, IMAGES)
    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Remove…")
    dialog = virtualbricks.find("dialog", REMOVE_IMAGE)
    virtualbricks.find("label", f"Remove the image {name}?", within=dialog)
    # then what becomes of their private copies
    loses = f"{disks[:1].upper()}{disks[1:]} will have no image."
    virtualbricks.wait_for(
        lambda: any(
            label.startswith(loses)
            for label in virtualbricks.names("label", within=dialog)
        ),
        f"the dialog says: {loses}",
    )
    return dialog


@when(words("I find the file of {name:Image}, {file} of my home folder"))
def find_file(virtualbricks, name, file):
    """
    Find the File…, in its menu, in the tab Images; in the dialog, which
    asks where the file is, the button of the file, then Home and the file
    in the file chooser, and Open; then Use This File, and the dialog
    closes.
    """

    on_tab(virtualbricks, IMAGES)
    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Find the File…")
    dialog = virtualbricks.find("dialog", FIND_FILE)
    where = f"Where is the file of {name}?"
    virtualbricks.find("label", where, within=dialog)
    choose_home_file(virtualbricks, dialog, CHOOSE_FILE, file)
    virtualbricks.click("button", "Use This File", within=dialog)
    virtualbricks.gone("dialog", FIND_FILE)


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
        for row in tab_rows(virtualbricks, IMAGES, NO_IMAGES)
    ]


@then("the list of images has")
def images_listed(virtualbricks, datatable):
    """
    Its rows, all of them and in order, once they are those of the table
    under the step, whose first line has the titles of the columns: each
    row has the name of the image, its detail, without the space its file
    takes, and its state.
    """

    has_rows(
        virtualbricks,
        "the list of images",
        lambda: image_rows(virtualbricks),
        datatable,
    )


def image_facts(virtualbricks):
    """
    The facts of the details of an image, {name: value}: each name a label,
    its value the label beside it, in the same row of their grid.
    """

    tab = virtualbricks.find("page tab", IMAGES)
    grid = virtualbricks.find("label", "File", within=tab).get_parent()
    rows = {}
    for label in harness.a11y.find_all(grid, "label"):
        x, y, _width, _height = harness.a11y.extents(label)
        rows.setdefault(y, []).append((x, label.get_name()))
    # the name, then the value
    return dict(
        tuple(name for _x, name in sorted(row)) for row in rows.values()
    )


def details_say(virtualbricks, name, wanted, facts):
    """The details of the image, once facts() of them are wanted."""

    tab = virtualbricks.find("page tab", IMAGES)
    entry = virtualbricks.find("text", "Name", within=tab)
    assert harness.a11y.text(entry) == name, f"not the details of {name}"
    try:
        virtualbricks.wait_for(
            lambda: facts() == wanted, f"the details of {name} say {wanted}"
        )
    except AssertionError:
        raise AssertionError(
            f"the details of {name} say {facts()}, not {wanted}"
        ) from None


@then(words("the details of {name:Image} have"))
def details_have(virtualbricks, name, datatable):
    """
    The facts of the table under the step, a name and a value each, are
    those of the details of the image, once it has read its file.
    """

    wanted = dict(datatable[1:])

    def facts():
        shown = image_facts(virtualbricks)
        return {fact: shown.get(fact) for fact in wanted}

    details_say(virtualbricks, name, wanted, facts)


@then(
    words(
        "the details of {name:Image} say what qemu-img info says of {file} of"
        " the image folder"
    )
)
def details_info(virtualbricks, name, file):
    """
    The facts of the details of the image are those of qemu-img info of the
    file: its path, its format, the size of its disk and the space it takes,
    its snapshots, if any; and when the file changed, which isn't of
    qemu-img.
    """

    path = os.path.join(virtualbricks.workspace, IMAGE_FOLDER, file)
    info = image_info(path)
    wanted = {
        "File": short_path(virtualbricks, path),
        "Format": info["format"],
        "Size": f"{human_size(info['virtual-size'])} disk,"
        f" {human_size(info['actual-size'])} on disk",
    }
    snapshots = [snapshot["name"] for snapshot in info.get("snapshots", ())]
    if snapshots:
        wanted["Snapshots"] = ", ".join(snapshots)

    def facts():
        # once the file is read, they say when it changed
        shown = image_facts(virtualbricks)
        return shown if shown.pop(CHANGED, None) else None

    details_say(virtualbricks, name, wanted, facts)


def image_info(path, shared=False):
    """
    What qemu-img info says of the file at path; shared, also while a
    machine has it, which locks it.
    """

    words = ["qemu-img", "info", "--output=json", path]
    if shared:
        words.insert(2, "-U")
    done = subprocess.run(words, capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def human_size(size):
    """A size in bytes as Virtualbricks says it: B, KB, MB or GB of 1000."""

    if size < 1000:
        return f"{size} B"
    for unit in ("KB", "MB", "GB"):
        size /= 1000
        if size < 1000 or unit == "GB":
            return f"{size:.1f} {unit}"


def short_path(virtualbricks, path):
    """A path as Virtualbricks says it: with ~ for the home."""

    if path.startswith(virtualbricks.home + os.sep):
        return "~" + path[len(virtualbricks.home) :]
    return path


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


@then(words("the image folder has no copy of {file}"))
def image_not_copied(virtualbricks, file):
    """
    The file of the home stays, and no file of the image folder of the
    workspace, if there is one, has its bytes.
    """

    original = os.path.join(virtualbricks.home, file)
    assert os.path.isfile(original), f"{original} is gone"
    folder = os.path.join(virtualbricks.workspace, IMAGE_FOLDER)
    with open(original, "rb") as theirs:
        data = theirs.read()
    for copy in glob.glob(os.path.join(folder, "*")):
        with open(copy, "rb") as ours:
            assert ours.read() != data, f"{copy} is a copy of {original}"


@then(words("the image folder has {file}, a {fmt} disk of {size:d} {unit}"))
def image_made(virtualbricks, file, fmt, size, unit):
    """
    The image folder of the workspace has the file, which qemu-img info
    says is of the format, with a disk of the size, up to a sector more.
    """

    path = os.path.join(virtualbricks.workspace, IMAGE_FOLDER, file)
    assert os.path.isfile(path), f"{path} is missing"
    info = image_info(path)
    assert info["format"] == fmt, f"{file} is {info['format']}, not {fmt}"
    least = size * UNITS[unit]
    virtual = info["virtual-size"]
    assert least <= virtual < least + 512, f"{file} has {virtual} bytes"


@then(words("{vm:Brick} runs on a private copy of {file} of the image folder"))
def runs_on_copy(virtualbricks, brick_processes, vm, file):
    """
    It runs, and a disk of its QEMU is a file of its own above the file of
    the image folder, as qemu-img info says: its private copy.
    """

    brick_running(virtualbricks, brick_processes, vm)
    image = os.path.join(virtualbricks.workspace, IMAGE_FOLDER, file)
    disks = []
    for pid in brick_processes[vm]:
        words = virtualbricks.command_line(pid)
        disks += [
            disk
            for option, disk in zip(words, words[1:])
            if option in DISK_OPTIONS
        ]
    assert disks, f"{vm} runs with no disk"
    above = []
    for disk in disks:
        info = image_info(disk, shared=True)
        backing = info.get("full-backing-filename")
        above.append(backing)
        if disk != image and backing == image:
            return
    raise AssertionError(f"the disks {disks} of {vm} are above {above}")


@then(words("the file {file} of the image folder is in the trash"))
def image_in_trash(virtualbricks, file):
    """
    The image folder of the workspace has the file no more, and the trash
    of the home has it: a .trashinfo that says where it was, and the file.
    """

    path = os.path.join(virtualbricks.workspace, IMAGE_FOLDER, file)
    virtualbricks.wait_for(
        lambda: not os.path.exists(path), f"the image folder has no {file}"
    )
    trash = os.path.join(virtualbricks.home, TRASH)
    trashed = trashed_as(trash, path)
    assert trashed is not None, f"the trash has no {path}"
    assert os.path.isfile(os.path.join(trash, "files", trashed))


@then(words("the image folder still has {file}, in no trash"))
def image_kept(virtualbricks, file):
    """The image folder of the workspace has the file, and the trash not."""

    path = os.path.join(virtualbricks.workspace, IMAGE_FOLDER, file)
    assert os.path.isfile(path), f"{path} is gone"
    trash = os.path.join(virtualbricks.home, TRASH)
    assert trashed_as(trash, path) is None, f"the trash has {path}"


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

    path = os.path.join(virtualbricks.workspace, IMAGE_FOLDER, file)
    has_image_file(virtualbricks, name, path)


@then(
    words(
        "project.toml has the image {name:Image}, of {file} of my home folder"
    )
)
def project_image_home(virtualbricks, name, file):
    """The same, with the file of the home."""

    has_image_file(virtualbricks, name, os.path.join(virtualbricks.home, file))


@then(
    words("project.toml has the disk {device} of {vm:Brick}, without an image")
)
def disk_without_image(virtualbricks, device, vm):
    """
    The disk of the machine, in the file of the project, is there, with no
    image.
    """

    disks = project_brick_of(virtualbricks, vm).get("disks", {})
    assert device in disks, f"{vm} has no disk {device}: {disks}"
    image = disks[device]["image"]
    assert image == "", f"the disk {device} of {vm} has the image {image}"


def has_image_file(virtualbricks, name, wanted):
    """
    The image in the file of the project has the file at wanted: its path,
    or one relative to the folder of the project.
    """

    path = project_path(virtualbricks)
    images = project_file(virtualbricks).get("images", {})
    assert name in images, f"project.toml has no image {name}: {images}"
    found = os.path.join(os.path.dirname(path), images[name]["path"])
    assert os.path.normpath(found) == wanted, f"{name} is of {found}"


# Events

EVENTS = "Events"
# What the tab Events says in place of its list, when there are no events
NO_EVENTS = "No Events Yet"
# The kind of an action that starts a brick, in the settings of an event
START_A_BRICK = "Start a brick"
# The state of an event in its row: waiting, before the seconds left, or
# ready
WAITING = "Waiting · "
READY = "Ready"
# The submenus of the menu of a brick that choose an event
WHEN_IT = ("When It Starts", "When It Stops")


@when(
    words(
        "I make an event that starts {brick:Brick} after {seconds:d}"
        " seconds, with the name it suggests, {name:Brick}"
    )
)
def make_event(virtualbricks, brick, seconds, name):
    """
    New Event, in the tab Events: the name must be the one the dialog
    suggests; the seconds typed in Wait, then Create; in the settings of the
    event, Add Action, Start a brick and the brick, then OK.
    """

    new_event(virtualbricks, name, seconds)
    virtualbricks.click("button", "Add Action")
    action = virtualbricks.find("combo box", START_A_BRICK).get_parent()
    if virtualbricks.shows("combo box", brick, within=action) is None:
        # the first brick, which it has at first
        combo = next(
            combo
            for combo in harness.a11y.find_all(action, "combo box")
            if combo.get_name() != START_A_BRICK
        )
        virtualbricks.click("combo box", combo.get_name(), within=action)
        virtualbricks.click("menu item", brick, within=combo)
    virtualbricks.find("combo box", brick, within=action)
    virtualbricks.click("button", "OK")
    virtualbricks.find("button", f"Start {name}")


@when(
    words(
        "I make an event that starts {brick:Brick} at once, with the name it"
        " suggests, {name:Brick}"
    )
)
def make_event_at_once(virtualbricks, brick, name):
    """The same, with 0 seconds in Wait."""

    make_event(virtualbricks, brick, 0, name)


@when(
    words(
        "I make an event without actions, with the name it suggests,"
        " {name:Brick}"
    )
)
def make_empty_event(virtualbricks, name):
    """
    New Event, in the tab Events: the name must be the one the dialog
    suggests; then Create, and OK in the settings of the event.
    """

    new_event(virtualbricks, name)
    virtualbricks.click("button", "OK")
    virtualbricks.find("button", f"Start {name}")


def new_event(virtualbricks, name, seconds=None):
    """
    New Event, in the tab Events: the name must be the one the dialog
    suggests; the seconds, if given, typed in Wait; then Create, and the
    settings of the event show.
    """

    on_tab(virtualbricks, EVENTS)
    virtualbricks.click("button", "New Event")
    dialog = virtualbricks.find("dialog", "New Event")
    suggests(virtualbricks, dialog, "Name", name)
    if seconds is not None:
        virtualbricks.type(
            str(seconds), "spin button", "Wait", within=dialog, over=True
        )
    virtualbricks.click("button", "Create", within=dialog)
    virtualbricks.gone("dialog", "New Event")
    virtualbricks.find("label", "Event settings")


@when(words("I start the event {name:Brick}"))
def start_event(virtualbricks, name):
    """Its Start, in the tab Events; then it waits: its Stop shows."""

    on_tab(virtualbricks, EVENTS)
    row = virtualbricks.row(name)
    virtualbricks.click("button", f"Start {name}", within=row)
    virtualbricks.find("button", f"Stop {name}", within=row)


@when(words("I stop the event {name:Brick} while it waits"))
def stop_event(virtualbricks, name):
    """
    Its Stop, in the tab Events, while its row says it waits; then its
    Start shows, and its row says Ready.
    """

    on_tab(virtualbricks, EVENTS)
    row = virtualbricks.row(name)
    state = event_state(row)
    assert state.startswith(WAITING), f"{name} doesn't wait: {state!r}"
    virtualbricks.click("button", f"Stop {name}", within=row)
    virtualbricks.find("button", f"Start {name}", within=row)
    virtualbricks.find("label", READY, within=row)


@when(words("I run the event {name:Brick} now, from its menu"))
def run_event_now(virtualbricks, name):
    """Run Now, in its menu, in the tab Events; then the menu closes."""

    on_tab(virtualbricks, EVENTS)
    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", "Run Now")
    virtualbricks.gone("button", "Run Now")


@when(
    words("I choose {event:Brick} in {submenu}, in the menu of {name:Brick}")
)
def choose_event(virtualbricks, event, submenu, name):
    """
    In the menu of the brick, When It Starts or When It Stops, then the
    event; then Escape closes the menu, which a choice leaves open. The
    choices of a menu of GTK 3 don't tell AT-SPI which is on: the row of
    the event says it.
    """

    assert submenu in WHEN_IT, f"{submenu} is none of {WHEN_IT}"
    virtualbricks.click("button", f"Menu of {name}")
    virtualbricks.click("button", submenu)
    virtualbricks.click("radio button", event)
    virtualbricks.key("Escape", virtualbricks.find("frame"))
    virtualbricks.gone("radio button", event)


def event_state(row):
    """What the row of an event says of it: Ready, Waiting · 2 s, …"""

    labels = list(harness.a11y.find_all(row, "label"))
    # after the name and the detail
    return labels[-1].get_name()


@then(
    words(
        "{name:Brick} counts down from {seconds:d} seconds, then starts"
        " {brick:Brick}"
    )
)
def counts_down(virtualbricks, name, seconds, brick):
    """
    The row of the event says that it waits, with the seconds left, from
    seconds down to 1, while no process of the brick runs; then it says
    Ready, and a process of the brick runs.
    """

    row = virtualbricks.row(name)
    said = []

    def ready():
        state = event_state(row)
        if state.startswith(WAITING) and virtualbricks.bricks(brick):
            # the brick starts as the row says Ready, not before
            state = event_state(row)
            assert not state.startswith(
                WAITING
            ), f"{brick} runs while the row of {name} says {state!r}"
        if not said or said[-1] != state:
            said.append(state)
        return state == READY

    virtualbricks.wait_for(
        ready,
        f"the row of {name} says {READY}",
        timeout=seconds + harness.TIMEOUT,
    )
    wanted = [f"{WAITING}{left} s" for left in range(seconds, 0, -1)]
    wanted.append(READY)
    assert said == wanted, f"the row of {name} said {said}, not {wanted}"
    virtualbricks.wait_for(
        lambda: virtualbricks.bricks(brick), f"a process of {brick} runs"
    )


@then("the list of events has")
def events_listed(virtualbricks, datatable):
    """
    The rows of the tab Events, all of them and in order, once they are
    those of the table under the step, whose first line has the titles of
    the columns: each row has the name of the event, its detail and its
    state.
    """

    has_rows(
        virtualbricks,
        "the list of events",
        lambda: tab_rows(virtualbricks, EVENTS, NO_EVENTS),
        datatable,
    )


# Topology

TOPOLOGY = "Topology"
# How far over the bottom of the tab a drag of the picture starts: under
# the bricks, which are a row in the middle of its height, where the
# background is
UNDER_THE_BRICKS = 30


# The tooltip of the zoom level of the tab Topology, which the screen
# readers say after the level
ZOOM_TO_100 = "Zoom to 100%"
# The title of the file chooser of Export as Image…
EXPORT_IMAGE = "Export as Image"
# The first bytes of a PNG file
PNG = b"\x89PNG\r\n\x1a\n"


@when(words("I zoom {way} on the picture of the lab {times:d} times"))
def zoom(virtualbricks, way, times):
    """The tab Topology, then its Zoom In, or Zoom Out, times."""

    assert way in ("in", "out"), f"zoom in or out, not {way}"
    tab = virtualbricks.click("page tab", TOPOLOGY)
    for _ in range(times):
        virtualbricks.click("button", f"Zoom {way.title()}", within=tab)


@when("I zoom the picture of the lab back to 100%")
def zoom_back(virtualbricks):
    """The tab Topology, then its zoom level, which zooms to 100%."""

    tab = virtualbricks.click("page tab", TOPOLOGY)
    level = zoom_level(virtualbricks, tab)
    virtualbricks.click("button", level.get_name(), within=tab)


@then(words("the zoom level of the picture of the lab is {level}"))
def zoom_level_is(virtualbricks, level):
    """The zoom level of the tab Topology says level, as 150%."""

    tab = virtualbricks.find("page tab", TOPOLOGY)
    button = zoom_level(virtualbricks, tab)
    try:
        virtualbricks.wait_for(
            lambda: button.get_name() == level, f"the zoom level is {level}"
        )
    except AssertionError:
        raise AssertionError(
            f"the zoom level is {button.get_name()}, not {level}"
        ) from None


def zoom_level(virtualbricks, tab):
    """
    The zoom level of the tab Topology, once it shows: a button named by
    the level, whose tooltip says it zooms to 100%.
    """

    return virtualbricks.wait_for(
        lambda: next(
            (
                button
                for button in harness.a11y.find_all(tab, "button")
                if button.get_description() == ZOOM_TO_100
            ),
            None,
        ),
        "the zoom level shows",
    )


@when(
    words(
        "I export the picture of the lab to {file} of my home folder, typing"
        " its path"
    )
)
def export_picture(virtualbricks, file):
    """
    The tab Topology, Export as Image… in its More; in the file chooser,
    the path typed in place of the name it suggests, then Save, and the file
    chooser closes.
    """

    tab = virtualbricks.click("page tab", TOPOLOGY)
    virtualbricks.click("toggle button", "More", within=tab)
    virtualbricks.click("button", "Export as Image…")
    chooser = virtualbricks.find("file chooser", EXPORT_IMAGE)
    path = os.path.join(virtualbricks.home, file)
    virtualbricks.type(path, "text", "Name:", within=chooser, over=True)
    virtualbricks.click("button", "Save", within=chooser)
    virtualbricks.gone("file chooser", EXPORT_IMAGE)


@then(words("the file {file} of my home folder is a PNG image, not blank"))
def png_image(virtualbricks, file):
    """
    The file is a PNG image, which cairo reads: a drawing, whose pixels
    aren't all alike.
    """

    path = os.path.join(virtualbricks.home, file)
    virtualbricks.wait_for(lambda: os.path.isfile(path), f"{path} is there")
    with open(path, "rb") as image:
        assert image.read(len(PNG)) == PNG, f"{file} isn't a PNG image"
    surface = cairo.ImageSurface.create_from_png(path)
    data = bytes(surface.get_data())
    pixels = {data[i : i + 4] for i in range(0, len(data), 4)}
    width, height = surface.get_width(), surface.get_height()
    assert len(pixels) > 1, f"{file} is blank, {width} × {height}"


@when(words("I drag the picture of the lab {pixels:d} pixels to the {side}"))
def drag_picture(virtualbricks, picture_scroll, pixels, side):
    """
    A press on the background of the picture, under its bricks, a move of
    pixels to the left or to the right, and a release; the picture is wider
    than the tab, which has a horizontal scroll bar.
    """

    pane, bar = picture_pane(virtualbricks)

    def ready():
        # where the picture is before the press, once a zoom just before
        # has scrolled it
        picture_scroll["before"] = harness.a11y.position(bar)[0]

    x, y, width, height = harness.a11y.extents(pane)
    start = (x + width // 2, y + height - UNDER_THE_BRICKS)
    shift = -pixels if side == "left" else pixels
    virtualbricks.drag(start, (start[0] + shift, start[1]), ready)


@then(words("the picture of the lab moved {pixels:d} pixels to the {side}"))
def picture_moved(virtualbricks, picture_scroll, pixels, side):
    """
    Its horizontal scroll bar moved as much the other way: the tab shows
    what was pixels further right of the picture, or further left.
    """

    _, bar = picture_pane(virtualbricks)
    before = picture_scroll["before"]
    wanted = before + pixels if side == "left" else before - pixels
    try:
        virtualbricks.wait_for(
            lambda: harness.a11y.position(bar)[0] == wanted,
            f"the picture of the lab moved {pixels} pixels to the {side}",
        )
    except AssertionError:
        now = harness.a11y.position(bar)[0]
        raise AssertionError(
            f"the picture is scrolled to {now}, from {before}, not {wanted}"
        ) from None


def picture_pane(virtualbricks):
    """
    The scroll pane of the picture of the lab, in the tab Topology, and its
    horizontal scroll bar, once it shows.
    """

    tab = virtualbricks.find("page tab", TOPOLOGY)
    pane = virtualbricks.find("scroll pane", within=tab)
    bar = virtualbricks.wait_for(
        lambda: next(
            (
                bar
                for bar in harness.a11y.find_all(pane, "scroll bar")
                if not harness.a11y.vertical(bar)
            ),
            None,
        ),
        "the picture of the lab is wider than its tab",
    )
    return pane, bar


# Readme

README_TAB = "Readme"
# The style of a run of text, as a user sees it, by its attributes as AT-SPI
# tells them, which the screen readers tell too
STYLES = (
    ("large", lambda attributes: float(attributes.get("scale", 1)) > 1),
    ("bold", lambda attributes: int(attributes.get("weight", 400)) >= 700),
    ("italic", lambda attributes: attributes.get("style") == "italic"),
    ("monospace", lambda attributes: attributes.get("family") == "monospace"),
)


@given(words("the project {name:Project} has the README"))
def project_readme(virtualbricks, name, docstring):
    """
    The folder of the project, in the workspace, has the file of the
    project, and a README with the text under the step; before
    Virtualbricks starts. The project that it opens at its first start is
    new_project.
    """

    assert virtualbricks.process is None, "Virtualbricks runs already"
    project = os.path.join(virtualbricks.workspace, name)
    os.makedirs(project, exist_ok=True)
    path = os.path.join(project, "project.toml")
    if not os.path.exists(path):
        with open(path, "w") as file:
            file.write("format = 2\n")
    with open(os.path.join(project, "README"), "w") as file:
        file.write(docstring + "\n")


@when(words("I open the tab {title}"))
def open_tab(virtualbricks, title):
    """Its page tab, in the main window; then it is the one that shows."""

    tab = virtualbricks.click("page tab", title)
    virtualbricks.wait_for(
        lambda: harness.a11y.selected(tab), f"the tab {title} shows"
    )


def on_tab(virtualbricks, title):
    """The tab title, clicked unless it is the one that shows."""

    tab = virtualbricks.find("page tab", title)
    if not harness.a11y.selected(tab):
        open_tab(virtualbricks, title)
    return tab


@when("I write the README in the Readme tab")
def write_readme(virtualbricks, docstring):
    """
    The tab Readme, its Edit, then the text under the step typed in its
    editor.
    """

    tab = virtualbricks.click("page tab", README_TAB)
    virtualbricks.click("radio button", "Edit", within=tab)
    editor = virtualbricks.wait_for(
        lambda: next(
            (
                text
                for text in harness.a11y.find_all(tab, "text")
                if harness.a11y.editable(text)
            ),
            None,
        ),
        "the editor of the README shows",
    )
    virtualbricks.type(docstring, "text", within=editor)


@when("I show the preview of the README")
def preview_readme(virtualbricks):
    """The Preview of the tab Readme."""

    tab = virtualbricks.find("page tab", README_TAB)
    virtualbricks.click("radio button", "Preview", within=tab)


@then("the Readme tab shows the README rendered")
def readme_rendered(virtualbricks, datatable):
    """
    The preview of the tab Readme has the runs of text of the table under
    the step, all of them and in order: the text of each, without the
    spaces at its ends, and its style, as large, bold, italic or monospace.
    """

    tab = virtualbricks.find("page tab", README_TAB)
    found = []

    def rendered():
        preview = next(
            (
                text
                for text in harness.a11y.find_all(tab, "text")
                if not harness.a11y.editable(text)
            ),
            None,
        )
        found[:] = [] if preview is None else preview_runs(preview)
        return datatable[:1] + found == datatable

    try:
        virtualbricks.wait_for(rendered, "the README shows rendered")
    except AssertionError:
        raise AssertionError(
            f"the preview has {found}, not {datatable[1:]}"
        ) from None


def preview_runs(preview):
    """
    The runs of text of a preview, a line at a time: the text of each,
    without the spaces at its ends, and its style.
    """

    found = []
    for text, attributes in harness.a11y.runs(preview):
        style = ", ".join(name for name, has in STYLES if has(attributes))
        for line in text.split("\n"):
            if line.strip():
                found.append([line.strip(), style])
    return found


@then(words("the README file of {name:Project} has"))
def readme_file(virtualbricks, name, docstring):
    """
    The README of the folder of the project, in the workspace, has the text
    under the step, once Virtualbricks has written it; the spaces at the
    end aside.
    """

    path = os.path.join(virtualbricks.workspace, name, "README")

    def text():
        try:
            with open(path, encoding="utf-8") as file:
                return file.read().rstrip()
        except FileNotFoundError:
            return None

    try:
        virtualbricks.wait_for(
            lambda: text() == docstring.rstrip(), f"{path} has the text"
        )
    except AssertionError:
        raise AssertionError(f"README has {text()!r}") from None


# Settings

# The title of the Settings window
SETTINGS_WINDOW = "Virtualbricks Settings"


@when(
    words(
        'I turn {state} "{setting}" in the Settings window, on its page'
        " {page}"
    )
)
def turn_setting(virtualbricks, state, setting, page):
    """
    Settings, in the menu File; on the page, the switch of the setting,
    which is the other way, turned on or off; then OK, and the window
    closes.
    """

    on = turned(state)
    dialog = open_settings(virtualbricks)
    switch = settings_switch(virtualbricks, dialog, page, setting)
    assert harness.a11y.checked(switch) != on, f"{setting} is already {state}"
    virtualbricks.click("toggle button", setting, within=dialog)
    virtualbricks.wait_for(
        lambda: harness.a11y.checked(switch) == on, f"{setting} is {state}"
    )
    virtualbricks.click("button", "OK", within=dialog)
    virtualbricks.gone("dialog", SETTINGS_WINDOW)


@when("I open the Settings window")
def open_settings_window(virtualbricks):
    """Settings, in the menu File."""

    open_settings(virtualbricks)


def open_settings(virtualbricks):
    """Settings, in the menu File: the window, once it shows."""

    virtualbricks.choose("Settings", "File")
    return virtualbricks.find("dialog", SETTINGS_WINDOW)


def settings_switch(virtualbricks, dialog, page, setting):
    """The switch of the setting, on the page of the Settings window."""

    virtualbricks.click("page tab", page, within=dialog)
    return virtualbricks.enabled("toggle button", setting, within=dialog)


def turned(state):
    """Whether a switch said on or off is on."""

    assert state in ("on", "off"), f"a switch is on or off, not {state}"
    return state == "on"


@then(words('the page {page} of the Settings window has "{setting}" {state}'))
def settings_shows(virtualbricks, page, setting, state):
    """The switch of the setting, on the page, is on or off."""

    dialog = virtualbricks.find("dialog", SETTINGS_WINDOW)
    switch = settings_switch(virtualbricks, dialog, page, setting)
    virtualbricks.wait_for(
        lambda: harness.a11y.checked(switch) == turned(state),
        f"{setting} is {state}",
    )


@then("settings.toml has")
def settings_toml(virtualbricks, datatable):
    """
    The settings file has the settings of the table under the step, a name
    and a value each, the value as TOML writes it.
    """

    toml_has(virtualbricks.settings, None, datatable)


@then("project.toml has the settings")
def project_settings(virtualbricks, datatable):
    """
    The file of the project has the settings of the table under the step, in
    its table settings, a name and a value each, the value as TOML writes
    it.
    """

    toml_has(project_path(virtualbricks), "settings", datatable)


def toml_has(path, table, datatable):
    """
    The file of path has the settings of datatable, at its top or in table,
    once Virtualbricks has written them.
    """

    wanted = {
        setting: tomllib.loads(f"value = {value}")["value"]
        for setting, value in datatable[1:]
    }

    def found():
        with open(path, "rb") as file:
            data = tomllib.load(file)
        if table is not None:
            data = data.get(table, {})
        return {setting: data.get(setting) for setting in wanted}

    name = os.path.basename(path)
    try:
        harness.a11y.wait_for(
            lambda: found() == wanted, f"{name} has {wanted}"
        )
    except AssertionError:
        raise AssertionError(f"{name} has {found()}, not {wanted}") from None


# A program that fails, and what Virtualbricks says of it


@given(words('a vde_switch that writes "{text}" and exits with {status:d}'))
def failing_switch(virtualbricks, text, status):
    """A vde_switch of its own, which writes text, and exits."""

    fake_switch(virtualbricks, [text], status)


@given(
    words("a vde_switch that writes these lines, and exits with {status:d}")
)
def failing_switch_lines(virtualbricks, docstring, status):
    """The same, with the lines of the text under the step."""

    fake_switch(virtualbricks, docstring.splitlines(), status)


def fake_switch(virtualbricks, lines, status):
    """
    A script of its own in place of vde_switch, in the folder of the VDE
    programs of the project that Virtualbricks opens at its first start,
    new_project: it writes the lines on its standard error, at once, and
    exits.
    """

    assert virtualbricks.process is None, "Virtualbricks runs already"
    folder = os.path.join(virtualbricks.home, "vde")
    os.makedirs(folder)
    program = os.path.join(folder, "vde_switch")
    words = " ".join(shlex.quote(line) for line in lines)
    with open(program, "w") as file:
        file.write(f"#!/bin/sh\nprintf '%s\\n' {words} >&2\nexit {status}\n")
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

    view = console(virtualbricks)

    def output():
        for line in harness.a11y.text(view).splitlines():
            fields = [field for field in line.split("\t") if field]
            if name in fields and (text in fields or f"2> {text}" in fields):
                return line
        return None

    virtualbricks.wait_for(output, f"the output of {name} is in the window")


# The arrow of a toggle of the messages window: folded, unfolded
FOLDED = "▸"
UNFOLDED = "▾"


@then(words('the messages window has the message of {name:Brick}: "{text}"'))
def messages_message(virtualbricks, name, text):
    """A line of its messages comes from the brick, and says text."""

    virtualbricks.wait_for(
        lambda: message_line(console(virtualbricks), name, text) is not None,
        f"the message of {name} is in the window",
    )


@then(
    words(
        'the messages window has the output of {name:Brick}: "{text}", and'
        " {count:d} more lines folded"
    )
)
def output_folded(virtualbricks, name, text, count):
    """
    A line of its messages is the first line of the output of the brick,
    text, and a toggle that says how many more lines it folds; no line of
    them shows under it.
    """

    view = console(virtualbricks)
    first = f"{output_of(text)}  {toggle(count, unfolded=False)}"

    def folded():
        index = message_line(view, name, first)
        if index is None:
            return False
        lines = harness.a11y.text(view).split("\n")
        # the next line, if any, is a message of its own
        return index + 1 == len(lines) or "\t" in lines[index + 1]

    virtualbricks.wait_for(folded, f"the output of {name} is folded")


@when(words("I unfold the output of {name:Brick} in the messages window"))
def unfold(virtualbricks, name):
    """
    The toggle of the output of the brick, after its first line; then it
    says the lines are unfolded.
    """

    view = console(virtualbricks)
    lines = harness.a11y.text(view).split("\n")
    index = next(
        (
            index
            for index, line in enumerate(lines)
            if source_of(line) == name
            and message_of(line).startswith(output_of(""))
            and FOLDED in line
        ),
        None,
    )
    assert index is not None, f"no output of {name} folded"
    line = lines[index]
    start = sum(len(before) + 1 for before in lines[:index])
    # the toggle: the arrow, up to the end of the line
    arrow = line.index(FOLDED)
    virtualbricks.click_text(view, start + arrow, len(line) - arrow)
    virtualbricks.wait_for(
        lambda: UNFOLDED in harness.a11y.text(view).split("\n")[index],
        f"the output of {name} is unfolded",
    )


@then(words("the messages window has the output of {name:Brick}, unfolded"))
def output_unfolded(virtualbricks, name, docstring):
    """
    A line of its messages is the first line of the output of the brick,
    and a toggle that says how many more lines it unfolded, which show under
    it: the lines of the text under the step.
    """

    view = console(virtualbricks)
    first, *more = docstring.splitlines()
    line = f"{output_of(first)}  {toggle(len(more), unfolded=True)}"

    def unfolded():
        index = message_line(view, name, line)
        if index is None:
            return False
        lines = harness.a11y.text(view).split("\n")
        return lines[index + 1 : index + 1 + len(more)] == more

    virtualbricks.wait_for(unfolded, f"the output of {name} is unfolded")


def console(virtualbricks):
    """The text of the messages window, once it shows."""

    window = virtualbricks.find("frame", "Logs")
    pane = virtualbricks.find("scroll pane", within=window)
    return virtualbricks.find("text", within=pane)


def message_line(view, name, text):
    """
    The index of the line of the messages window that comes from name and
    says text, or None. A message is a line of fields, after tabs: its time,
    where it comes from, its text; the lines a toggle unfolds have none.
    """

    for index, line in enumerate(harness.a11y.text(view).split("\n")):
        if source_of(line) == name and message_of(line) == text:
            return index
    return None


def source_of(line):
    """Where a message comes from, or None for a line that isn't one."""

    fields = [field for field in line.split("\t") if field]
    return fields[1] if len(fields) == 3 else None


def message_of(line):
    """The text of a message, after where it comes from."""

    return [field for field in line.split("\t") if field][-1]


def output_of(text):
    """A line that a program wrote on its standard error, as it shows."""

    return f"2> {text}"


def toggle(count, unfolded):
    """
    The toggle of count lines of a message, as the messages window says it:
    an arrow, to the right when folded, down when unfolded.
    """

    arrow = UNFOLDED if unfolded else FOLDED
    lines = "line" if count == 1 else "lines"
    # never broken over two lines
    return f"{arrow} {count} more {lines}".replace(" ", "\u00a0")


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


@given(
    words("the project {name:Project} of Virtualbricks 2.1, whose .project is")
)
def old_project_text(virtualbricks, old_files, name, docstring):
    """A folder name in the workspace, with the text under the step."""

    write_old(virtualbricks, old_files, f"{name}/.project", docstring + "\n")


@given(
    words(
        "the project {name:Project} of Virtualbricks 2.1, as the single file"
        " {file} in the workspace"
    )
)
def old_single_file(virtualbricks, old_files, name, file):
    """
    The .project of projects/NAME, as a file of the workspace: so the
    versions before 2.1 kept a project, and 2.1 still opened it.
    """

    with open(os.path.join(PROJECTS, name, ".project")) as project:
        write_old(virtualbricks, old_files, file, project.read())


def write_old(virtualbricks, old_files, path, text):
    """The file path of the workspace has text; old_files keeps it."""

    full = os.path.join(virtualbricks.workspace, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as file:
        file.write(text)
    with open(full, "rb") as file:
        old_files[path] = file.read()


@given(
    words(
        "the projects {first:Project} to {last:Project} of Virtualbricks 2.1,"
        " copies of {name:Project}"
    )
)
def old_copies(virtualbricks, first, last, name):
    """
    Copies of projects/NAME in the workspace, from first to last: a word
    and a number, of as many digits in both.
    """

    word, start = re.fullmatch(r"(.*?)(\d+)", first).groups()
    same, end = re.fullmatch(r"(.*?)(\d+)", last).groups()
    assert (same, len(end)) == (word, len(start)), f"not {first} to {last}"
    for number in range(int(start), int(end) + 1):
        shutil.copytree(
            os.path.join(PROJECTS, name),
            os.path.join(
                virtualbricks.workspace, f"{word}{number:0{len(start)}d}"
            ),
        )


def old_projects(virtualbricks):
    """The folders of the workspace with a project of 2.1, by name."""

    return sorted(
        name
        for name in os.listdir(virtualbricks.workspace)
        if os.path.isfile(
            os.path.join(virtualbricks.workspace, name, ".project")
        )
    )


def project_toml_of(virtualbricks, name):
    """The time and the bytes of the project.toml of name, or None."""

    path = os.path.join(virtualbricks.workspace, name, "project.toml")
    try:
        with open(path, "rb") as file:
            return os.stat(file.fileno()).st_mtime_ns, file.read()
    except FileNotFoundError:
        return None


@when(words("I select {name:Project} in the migration window"))
def select_migrated(virtualbricks, name):
    """Its row in the list; then the messages under it are those of name."""

    window = virtualbricks.find("frame", MIGRATION)
    virtualbricks.click("table cell", name, within=window)
    virtualbricks.wait_for(
        lambda: migration_messages(virtualbricks)[:1] == [name],
        f"the messages of {name} show",
    )


def migration_messages(virtualbricks):
    """
    The lines under the list of the migration window: the name of the row
    selected, then its messages.
    """

    window = virtualbricks.find("frame", MIGRATION)
    # after the entries of the form, over the list
    view = list(harness.a11y.find_all(window, "text"))[-1]
    return harness.a11y.text(view).splitlines()


@then(
    words('the migration window shows the {level} of {name:Project}: "{text}"')
)
def migration_shows(virtualbricks, level, name, text):
    """
    Under the list, the messages are those of name, and one is the text, of
    level: error, warning or info.
    """

    assert level in ("error", "warning", "info"), f"no level {level}"
    line = f"{level}  {text}"
    try:
        virtualbricks.wait_for(
            lambda: migration_messages(virtualbricks)[:1] == [name]
            and line in migration_messages(virtualbricks)[1:],
            f"the migration window shows the {level} of {name}",
        )
    except AssertionError:
        raise AssertionError(
            f"the migration window shows {migration_messages(virtualbricks)},"
            f" not {name} and {line!r}"
        ) from None


@then(words("{name:Project} isn't migrated"))
def not_migrated(virtualbricks, name):
    """Its folder in the workspace has no project.toml."""

    path = os.path.join(virtualbricks.workspace, name, "project.toml")
    assert not os.path.exists(path), f"{path} is there"


@then(words("the old file {path} of the workspace stays as it was"))
def old_file_kept(virtualbricks, old_files, path):
    """It has the bytes that a step wrote there before Virtualbricks ran."""

    with open(os.path.join(virtualbricks.workspace, path), "rb") as file:
        data = file.read()
    assert data == old_files[path], f"{path} has {data!r}"


@when("I close the migration window while it migrates")
def close_while_migrating(virtualbricks, migrated_before):
    """
    Its button Close, once a project has its project.toml, as its files
    say: the window answers AT-SPI only between two projects. Then
    migrated_before has those that it migrated.
    """

    window = virtualbricks.find("frame", MIGRATION)
    # the last row of the window, after its title bar: a search through
    # the list over it would ask the window for each of its cells
    box = last_child(window)
    buttons = last_child(box)
    virtualbricks.wait_for(
        lambda: any(
            project_toml_of(virtualbricks, name)
            for name in old_projects(virtualbricks)
        ),
        "a project is migrated",
    )
    virtualbricks.click("button", "Close", within=buttons)
    virtualbricks.gone("frame", MIGRATION)
    for name in old_projects(virtualbricks):
        done = project_toml_of(virtualbricks, name)
        if done is not None:
            migrated_before[name] = done


def last_child(accessible):
    """The last of its children, as the widgets show them."""

    return accessible.get_child_at_index(accessible.get_child_count() - 1)


@then("some of the projects are migrated, and the others not")
def some_migrated(virtualbricks, migrated_before):
    """
    The old projects that have their project.toml are those migrated before
    the window closed, as they were then: the migration stopped there; the
    others have none.
    """

    names = old_projects(virtualbricks)
    assert migrated_before, "no project is migrated"
    assert len(migrated_before) < len(
        names
    ), f"all the {len(names)} projects are migrated: it was closed too late"
    now = {
        name: project_toml_of(virtualbricks, name)
        for name in names
        if project_toml_of(virtualbricks, name) is not None
    }
    after = sorted(name for name in now if name not in migrated_before)
    assert not after, f"migrated once the window closed: {after}"
    assert now == migrated_before, "a project.toml changed once it closed"


@then(
    "the projects not migrated before are migrated, and the others stay as"
    " they were"
)
def rest_migrated(virtualbricks, migrated_before):
    """
    The migration ends, as Save report… says; each old project has its
    project.toml, and those migrated before the same, not written again.
    """

    window = virtualbricks.find("frame", MIGRATION)
    virtualbricks.enabled("button", "Save report…", within=window)
    for name in old_projects(virtualbricks):
        done = project_toml_of(virtualbricks, name)
        assert done is not None, f"{name} has no project.toml"
        if name in migrated_before:
            assert done == migrated_before[name], f"{name} migrated again"


# The title of the file chooser of Save report…
SAVE_REPORT = "Save report"


@when(
    words(
        "I save the report of the migration to {file} of my home folder,"
        " typing its path"
    )
)
def save_report(virtualbricks, file):
    """
    Save report…; in the file chooser, the path typed in place of the name
    that it suggests, then Save, and the file chooser closes.
    """

    window = virtualbricks.find("frame", MIGRATION)
    virtualbricks.click("button", "Save report…", within=window)
    chooser = virtualbricks.find("file chooser", SAVE_REPORT)
    path = os.path.join(virtualbricks.home, file)
    virtualbricks.type(path, "text", "Name:", within=chooser, over=True)
    virtualbricks.click("button", "Save", within=chooser)
    virtualbricks.gone("file chooser", SAVE_REPORT)


@then(words("the file {file} of my home folder has"))
def home_file_has(virtualbricks, file, docstring):
    """
    It has the text under the step, line by line; the spaces at the end of
    a line aside.
    """

    path = os.path.join(virtualbricks.home, file)
    virtualbricks.wait_for(lambda: os.path.isfile(path), f"{path} is there")
    with open(path, encoding="utf-8") as text:
        found = [line.rstrip() for line in text.read().splitlines()]
    wanted = [line.rstrip() for line in docstring.splitlines()]
    assert found == wanted, f"{file} has\n" + "\n".join(found)


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
