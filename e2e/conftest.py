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
step, the widgets that show and the output of Virtualbricks.
"""

import os
import shutil

import pytest

import harness

# the step definitions are fixtures, for every scenario
pytest_plugins = ["steps"]


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
def virtualbricks(desktop, tmp_path):
    """A Virtualbricks, not started; stopped at the end, with its screen."""

    vb = harness.Virtualbricks(
        desktop, str(tmp_path), str(tmp_path / "output.log")
    )
    try:
        yield vb
    finally:
        vb.stop()


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


def pytest_bdd_step_error(request, feature, scenario, step, exception):
    """The report of a step that failed, while Virtualbricks still shows."""

    vb = request.getfixturevalue("virtualbricks")
    print(f"The step that failed: {step.keyword} {step.name}")
    print("The widgets that show:", vb.describe(), sep="\n")
    if os.path.exists(vb.log):
        with open(vb.log, errors="replace") as file:
            print("The output of Virtualbricks:", file.read(), sep="\n")
