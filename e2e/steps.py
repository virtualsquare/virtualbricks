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
    """The words of a step, where {name:Brick} is the name of a brick."""

    return parsers.parse(text, extra_types={"Brick": brick})


@pytest.fixture
def brick_processes():
    """The processes of each brick that a step started: {name: pids}."""

    return {}


# Virtualbricks


@given("Virtualbricks is running")
def virtualbricks_running(virtualbricks):
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


# Bricks


@when(words("I add the {kind} {name:Brick}"))
def add_brick(virtualbricks, kind, name):
    """New Brick, then the kind; its settings, if any, as they are."""

    virtualbricks.click("button", "New Brick")
    # "virtual machine" is the row "Virtual machine"
    virtualbricks.click("label", kind[:1].upper() + kind[1:])
    virtualbricks.find("label", name)
    if virtualbricks.shows("button", "OK"):
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


@then(words("{name:Brick} is stopped"))
def brick_stopped(virtualbricks, brick_processes, name):
    """Its row says so, and the processes of its start have quit."""

    row = virtualbricks.row(name)
    virtualbricks.find("label", "Stopped", within=row)
    virtualbricks.find("button", f"Start {name}", within=row)
    pids = brick_processes.get(name, set())
    virtualbricks.wait_for(
        lambda: not pids & virtualbricks.children(),
        f"the processes of {name} quit",
    )


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
