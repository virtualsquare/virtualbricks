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
The fixtures of the end-to-end tests, and their steps: see README.md
and STEPS.md.

desktop is the buses that every scenario shares; virtualbricks is the
Virtualbricks of one scenario, which a Given step starts on a screen of its
own, and other_virtualbricks another one of the same user, beside it. The
steps are in :mod:`steps`. When a step fails, the report has the step, the
widgets that show and the output of each Virtualbricks, and the folder of
each a screenshot and a video of its screen (:mod:`recording`); with
--record-all, every scenario has them. With --alluredir=, the results of
Allure have them too.
"""

import os
import shutil
import time

import allure
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
# Of a scenario: the other Virtualbricks, if it has one.
OTHER = pytest.StashKey[harness.Virtualbricks]()
# Of the run: what was recorded, (scenario, lines).
RECORDED = pytest.StashKey[list]()
# In pytest's cache: how long each test took in the runs before, in
# seconds, by its node id without parameters.
DURATIONS = "e2e/durations"
# Set in the processes of pytest-xdist that run the tests: its name, and
# how many there are.
WORKER = "PYTEST_XDIST_WORKER"
WORKERS = "PYTEST_XDIST_WORKER_COUNT"
# What each test of this run took: its setup, its call and its teardown.
took = {}


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

    vb = harness.Virtualbricks(desktop, str(tmp_path))
    vb.make_home()
    try:
        yield vb
    finally:
        vb.stop()
        _record(request, vb)


@pytest.fixture
def other_virtualbricks(virtualbricks, tmp_path, request):
    """
    Another Virtualbricks of the same user, not started: the same home,
    settings and workspace, its files in the folder other of the scenario.
    Stopped first at the end, with its screen; the bricks that are left, the
    first one stops them.
    """

    vb = virtualbricks.beside(str(tmp_path / "other"))
    request.node.stash[OTHER] = vb
    try:
        yield vb
    finally:
        vb.stop(bricks=False)
        _record(request, vb, " of the other Virtualbricks")


def _record(request, vb, of=""):
    """
    The screenshot and the video of its screen, in its folder, and attached
    to the result of Allure; of says which Virtualbricks, but for the first.
    """

    steps = request.node.stash.get(STEPS, [])
    failed = any(failed for _, _, failed in steps)
    if vb.browser is None:
        return
    if not (failed or request.config.getoption("record_all")):
        return
    until = request.node.stash.get(ENDED, time.monotonic())
    try:
        lines = recording.record(
            vb.timeline(), steps, until, broadway.SCREEN, vb.folder
        )
    except Exception as error:
        # a scenario doesn't fail for its recording
        lines = [f"not recorded: {error!r}"]
    request.config.stash.setdefault(RECORDED, []).append(
        (request.node.nodeid, lines)
    )
    for name, kind in (
        ("screenshot.png", allure.attachment_type.PNG),
        ("recording.webm", allure.attachment_type.WEBM),
    ):
        path = os.path.join(vb.folder, name)
        if os.path.exists(path):
            allure.attach.file(path, name=name + of, attachment_type=kind)


def pytest_collection_modifyitems(config, items):
    """
    Under pytest-xdist, the tests in an order that keeps the workers busy
    alike, by what they took in the runs before.

    When the tests are fewer than two a worker, pytest-xdist deals them
    round the workers, one at a time: the workers get the longest tests
    first, the longest of all last of that round, and the first workers a
    second test, among the shortest. Else it sends each worker a few tests
    side by side first, two at least, then one at a time as they end: the
    longest, the shortest, the second longest, the second shortest, and so
    on. Two long scenarios side by side ran one after the other on a worker
    while the others had ended, and -n 8 took as long as -n 4.

    A test without a duration takes as long as the others on average; with
    none at all, the tests are alike, and the scenarios, collected first,
    end up between the tests of recording.py.
    """

    if WORKER not in os.environ:
        return
    cache = getattr(config, "cache", None)
    durations = {} if cache is None else cache.get(DURATIONS, {})
    known = [
        durations[bare(item.nodeid)]
        for item in items
        if bare(item.nodeid) in durations
    ]
    guess = sum(known) / len(known) if known else 0.0
    ranked = sorted(
        items,
        key=lambda item: durations.get(bare(item.nodeid), guess),
        reverse=True,
    )
    workers = int(os.environ[WORKERS])
    if len(ranked) < 2 * workers:
        items[:] = ranked[:workers][::-1] + ranked[workers:]
        return
    items[:] = []
    while ranked:
        items.append(ranked.pop(0))
        if ranked:
            items.append(ranked.pop())


def pytest_runtest_logreport(report):
    took[report.nodeid] = took.get(report.nodeid, 0.0) + report.duration


def pytest_sessionfinish(session):
    """What the tests took joins what they took before, in pytest's cache."""

    cache = getattr(session.config, "cache", None)
    if cache is None or WORKER in os.environ or not took:
        return
    durations = cache.get(DURATIONS, {})
    for nodeid, seconds in took.items():
        durations[bare(nodeid)] = seconds
    cache.set(DURATIONS, durations)


def bare(nodeid):
    """
    The node id of a test without its parameters: the same for each run of
    --count and each example of an outline.
    """

    return nodeid.partition("[")[0]


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
    _report(vb)
    other = request.node.stash.get(OTHER, None)
    if other is not None:
        _report(other, " of the other Virtualbricks")


def _report(vb, of=""):
    """
    Its screen, the widgets that show and its output, for a step that
    failed; of says which Virtualbricks, but for the first.
    """

    if vb.browser is not None:
        print(
            f"Its screen{of}: screenshot.png and recording.webm in", vb.folder
        )
        print(f"The widgets that show{of}:", vb.describe(), sep="\n")
    if os.path.exists(vb.log):
        with open(vb.log, errors="replace") as file:
            output = file.read()
        print(f"The output{of or ' of Virtualbricks'}:", output, sep="\n")


def pytest_terminal_summary(terminalreporter, config):
    """The screenshots and the videos of the run."""

    recorded = config.stash.get(RECORDED, [])
    if recorded:
        terminalreporter.section("screenshots and videos")
        for scenario, lines in recorded:
            terminalreporter.write_line(scenario)
            for line in lines:
                terminalreporter.write_line(f"  {line}")
