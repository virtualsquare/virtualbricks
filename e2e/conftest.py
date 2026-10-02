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
The fixtures of the end-to-end tests, and their steps: see README.md.

desktop is the buses that every scenario shares; virtualbricks is the
Virtualbricks of one scenario, which a Given step starts on a screen of its
own. The steps are in :mod:`steps`. When a step fails, the report has the
step, the widgets that show and the output of Virtualbricks, and the folder
of the scenario a screenshot and a video of its screen (:mod:`recording`);
with --record-all, every scenario has them.
"""

import os
import shutil
import time

import pytest

import broadway
import harness
import recording

# the step definitions are fixtures, for every scenario
pytest_plugins = ["steps"]

# Of a scenario: its steps as they began or failed, (time, step, failed),
# and when the last one ended.
STEPS = pytest.StashKey[list]()
ENDED = pytest.StashKey[float]()
# Of the run: what was recorded, (scenario, lines).
RECORDED = pytest.StashKey[list]()


def pytest_addoption(parser):
    parser.addoption(
        "--record-all",
        action="store_true",
        help="a screenshot and a video of each scenario, not only of those "
        "that fail",
    )


@pytest.fixture(scope="session")
def desktop(tmp_path_factory):
    lacking = harness.missing()
    if lacking:
        pytest.skip(f"not installed: {', '.join(lacking)}")
    desktop = harness.Desktop(str(tmp_path_factory.mktemp("desktop")))
    with pytest.MonkeyPatch.context() as patch:
        # AT-SPI in this process: the accessibility bus of the session bus
        # of the tests, never that of the desktop
        for name in harness.DESKTOP:
            patch.delenv(name, raising=False)
        try:
            desktop.start()
            patch.setenv(
                "DBUS_SESSION_BUS_ADDRESS",
                desktop.env["DBUS_SESSION_BUS_ADDRESS"],
            )
            yield desktop
        finally:
            desktop.stop()


@pytest.fixture
def virtualbricks(desktop, tmp_path, request):
    """
    A Virtualbricks, not started; stopped at the end, with its screen, which
    is recorded if a step failed, or with --record-all.
    """

    vb = harness.Virtualbricks(
        desktop, str(tmp_path), str(tmp_path / "output.log")
    )
    try:
        yield vb
    finally:
        vb.stop()
        _record(request, vb)


def _record(request, vb):
    steps = request.node.stash.get(STEPS, [])
    failed = any(failed for _, _, failed in steps)
    if vb.browser is None:
        return
    if not (failed or request.config.getoption("record_all")):
        return
    until = request.node.stash.get(ENDED, time.monotonic())
    try:
        lines = recording.record(
            vb.timeline(), steps, until, broadway.SCREEN, vb.home
        )
    except Exception as error:
        # a scenario doesn't fail for its recording
        lines = [f"not recorded: {error!r}"]
    request.config.stash.setdefault(RECORDED, []).append(
        (request.node.nodeid, lines)
    )


def pytest_bdd_apply_tag(tag, function):
    """@needs-PROGRAM: the scenario is skipped without PROGRAM."""

    if not tag.startswith("needs-"):
        return None
    program = tag[len("needs-") :]
    skip = pytest.mark.skipif(
        shutil.which(program) is None, reason=f"not installed: {program}"
    )
    skip(function)
    return True


def pytest_bdd_before_step(request, step):
    request.node.stash.setdefault(STEPS, []).append(
        (time.monotonic(), f"{step.keyword} {step.name}", False)
    )


def pytest_bdd_after_step(request):
    request.node.stash[ENDED] = time.monotonic()


def pytest_bdd_step_error(request, feature, scenario, step, exception):
    """The report of a step that failed, while Virtualbricks still shows."""

    now = time.monotonic()
    request.node.stash[ENDED] = now
    request.node.stash.setdefault(STEPS, []).append(
        (now, f"{step.keyword} {step.name}", True)
    )
    vb = request.getfixturevalue("virtualbricks")
    print(f"The step that failed: {step.keyword} {step.name}")
    print(f"Its screen: screenshot.png and recording.webm in {vb.home}")
    print("The widgets that show:", vb.describe(), sep="\n")
    if os.path.exists(vb.log):
        with open(vb.log, errors="replace") as file:
            print("The output of Virtualbricks:", file.read(), sep="\n")


def pytest_terminal_summary(terminalreporter, config):
    """The screenshots and the videos of the run."""

    recorded = config.stash.get(RECORDED, [])
    if recorded:
        terminalreporter.section("screenshots and videos")
        for scenario, lines in recorded:
            terminalreporter.write_line(scenario)
            for line in lines:
                terminalreporter.write_line(f"  {line}")
