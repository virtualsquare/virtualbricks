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
What the steps of the scenarios drive: a Virtualbricks of this checkout, on
a screen nobody sees.

Desktop is what the tests share: a session bus, with its accessibility bus.
Virtualbricks is the program of one scenario, with a HOME, a workspace and
settings of its own, and a Screen: broadwayd, GTK's HTML5 display server,
with the browser of :mod:`broadway`. Its widgets are found as a screen
reader finds them (:mod:`a11y`) and clicked through broadwayd. Nothing
reaches the desktop, nor a Virtualbricks that runs there.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile

import broadway

try:
    import a11y
except ValueError:
    # no AT-SPI typelib
    a11y = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAMS = ("broadwayd", "dbus-daemon")
A11Y_BUS = "/usr/share/dbus-1/services/org.a11y.Bus.service"
# Seconds: Virtualbricks shows its window, and quits; a widget shows.
START_TIMEOUT = 30
QUIT_TIMEOUT = 30
TIMEOUT = 10
# The first settings of each Virtualbricks: no alert of missing programs,
# which depends on the machine and stops the clicks on the main window.
SETTINGS = "format = 1\nwarn_missing_programs = false\n"
# GTK without animations: a popover shows at once where it ends up.
GTK_SETTINGS = "[Settings]\ngtk-enable-animations = 0\n"
# Out of the environment of the tests and of Virtualbricks: the screen and
# the buses of the desktop.
DESKTOP = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "AT_SPI_BUS_ADDRESS",
    "NO_AT_BRIDGE",
    "DBUS_SESSION_BUS_ADDRESS",
)


def missing():
    """What the tests need and this machine lacks."""

    names = [name for name in PROGRAMS if shutil.which(name) is None]
    if not os.path.exists(A11Y_BUS):
        names.append("at-spi2-core")
    if a11y is None:
        names.append("gir1.2-atspi-2.0")
    return names


class Desktop:
    """The session bus that the tests share, and their screens."""

    def __init__(self, logs):
        # short: the sockets of the bricks are in there too
        self.runtime = tempfile.mkdtemp(prefix="vb-e2e-")
        self.logs = logs
        self.bus = None
        self.screens = 0
        self.env = {
            name: value
            for name, value in os.environ.items()
            if name not in DESKTOP
        }
        self.env["XDG_RUNTIME_DIR"] = self.runtime

    def start(self):
        log = os.path.join(self.logs, "dbus.log")
        self.bus = _spawn(
            log,
            self.env,
            "dbus-daemon",
            "--session",
            "--nofork",
            "--print-address",
            f"--address=unix:path={self.runtime}/bus",
            stdout=subprocess.PIPE,
        )
        # printed once the bus listens
        address = self.bus.stdout.readline().decode().strip()
        if not address:
            raise RuntimeError(f"dbus-daemon didn't start: see {log}")
        self.env["DBUS_SESSION_BUS_ADDRESS"] = address

    def stop(self):
        if self.bus is not None:
            _stop(self.bus)
        shutil.rmtree(self.runtime, ignore_errors=True)

    def screen(self, log):
        """
        A screen of its own for a Virtualbricks: broadwayd aborts when a
        program it shows quits ("can't write to client").
        """

        self.screens += 1
        display = f":{self.screens}"
        http = os.path.join(self.runtime, f"http{self.screens}")
        process = _spawn(
            log, self.env, "broadwayd", "--unixsocket", http, display
        )
        try:
            a11y.wait_for(lambda: os.path.exists(http), "broadwayd listens")
            return Screen(display, process, broadway.Browser(http))
        except BaseException:
            _stop(process)
            raise


class Screen:
    """A broadwayd, on display, and its browser."""

    def __init__(self, display, process, browser):
        self.display = display
        self.process = process
        self.browser = browser

    def close(self):
        self.browser.close()
        _stop(self.process)


class Virtualbricks:
    """A Virtualbricks of this checkout, on the screen of the tests."""

    def __init__(self, desktop, home, log):
        self.desktop = desktop
        self.screen = None
        self.browser = None
        self.home = home
        self.config = os.path.join(home, ".config")
        # without it, the start is the first, as after Virtualbricks 2.1
        self.settings = os.path.join(
            self.config, "virtualbricks", "settings.toml"
        )
        self.workspace = os.path.join(home, "workspace")
        self.log = log
        self.process = None
        self.app = None
        for folder, name, text in (
            ("virtualbricks", "settings.toml", SETTINGS),
            ("gtk-3.0", "settings.ini", GTK_SETTINGS),
        ):
            os.makedirs(os.path.join(self.config, folder))
            with open(os.path.join(self.config, folder, name), "w") as file:
                file.write(text)
        os.makedirs(self.workspace)

    def start(self):
        """Start Virtualbricks on a screen, and wait for its main window."""

        self.screen = self.desktop.screen(
            os.path.join(self.home, "broadway.log")
        )
        self.browser = self.screen.browser
        env = dict(
            self.desktop.env,
            GDK_BACKEND="broadway",
            BROADWAY_DISPLAY=self.screen.display,
            HOME=self.home,
            XDG_CONFIG_HOME=self.config,
            XDG_STATE_HOME=os.path.join(self.home, ".local", "state"),
            XDG_DATA_HOME=os.path.join(self.home, ".local", "share"),
            XDG_CACHE_HOME=os.path.join(self.home, ".cache"),
            # the words of the steps: no translation
            LANGUAGE="C",
            LC_ALL="C.UTF-8",
            # nothing of the desktop's: no dconf, no gvfs
            GSETTINGS_BACKEND="memory",
            GIO_USE_VFS="local",
            # E2E_PYTHONPATH first: a sitecustomize.py there can break
            # Virtualbricks, to see a scenario fail
            PYTHONPATH=os.pathsep.join(
                filter(None, [os.environ.get("E2E_PYTHONPATH"), ROOT])
            ),
        )
        with open(self.log, "wb") as out:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "virtualbricks",
                    "--noterm",
                    "--lock",
                    "none",
                    "--workspace",
                    self.workspace,
                ],
                env=env,
                cwd=ROOT,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        # only this process: AT-SPI shows the other applications of the bus
        self.app = self.wait_for(
            lambda: a11y.application(self.process.pid),
            "Virtualbricks is on the accessibility bus",
            START_TIMEOUT,
        )
        self.find("frame", timeout=START_TIMEOUT)

    def stop(self):
        """Stop Virtualbricks, if it still runs, its bricks and its screen."""

        if self.process is not None:
            _stop(self.process, QUIT_TIMEOUT)
            for pid in self.bricks():
                os.kill(pid, signal.SIGKILL)
        if self.screen is not None:
            self.screen.close()

    # What the user sees and does

    def find(self, role, name=None, within=None, timeout=TIMEOUT):
        """
        The widget of role, and of name if given, once it shows, in within
        or anywhere.
        """

        what = f"a {role}" if name is None else f"the {role} {name!r}"
        return self.wait_for(
            lambda: self.shows(role, name, within),
            f"{what} shows",
            timeout,
        )

    def gone(self, role, name=None, within=None, timeout=TIMEOUT):
        """Wait until no widget of role, and of name if given, shows."""

        what = f"a {role}" if name is None else f"the {role} {name!r}"
        self.wait_for(
            lambda: self.shows(role, name, within) is None,
            f"{what} doesn't show",
            timeout,
        )

    def shows(self, role, name=None, within=None):
        """The widget of role, and of name if given, if it shows now."""

        return a11y.find(within or self.app, role, name)

    def names(self, role, within=None):
        """The names of the widgets of role that show now, in within."""

        return [
            widget.get_name()
            for widget in a11y.find_all(within or self.app, role)
        ]

    def enabled(self, role, name=None, within=None):
        """The widget, once it shows and is enabled."""

        widget = self.find(role, name, within)
        self.wait_for(
            lambda: a11y.sensitive(widget),
            f"the {role} {name!r} is enabled",
        )
        return widget

    def click(self, role, name=None, within=None):
        """Click in the middle of the widget, once it shows and is enabled."""

        widget = self.enabled(role, name, within)
        self.browser.click(*a11y.center(widget))
        return widget

    def choose(self, item, menu):
        """Click the menu of the menu bar, then its item."""

        self.click("menu", menu)
        self.click("menu item", item)

    def row(self, name):
        """The row of the list that is named name, once it shows."""

        def holding():
            for row in a11y.find_all(self.app, "list item"):
                if a11y.find(row, "label", name) is not None:
                    return row
            return None

        return self.wait_for(holding, f"the row of {name} shows")

    def rows(self, within):
        """
        The rows of the list in within, a scroll pane, from the first to the
        last, each the names of its labels. A row scrolled out of the pane
        doesn't show: the wheel scrolls the pane to its top, then down to
        its bottom, as a user does.
        """

        rows = {}

        def read():
            for row in a11y.find_all(within, "list item"):
                rows[a11y.index(row)] = self.names("label", within=row)

        bars = [
            bar
            for bar in a11y.find_all(within, "scroll bar")
            if a11y.vertical(bar)
        ]
        if bars:
            bar = bars[0]
            while a11y.position(bar)[0] > a11y.position(bar)[1]:
                self._turn(within, bar, down=False)
            read()
            while a11y.position(bar)[0] < a11y.position(bar)[2]:
                self._turn(within, bar, down=True)
                read()
        else:
            # all of it shows
            read()
        return [rows[index] for index in sorted(rows)]

    def _turn(self, pane, bar, down):
        """A turn of the wheel over pane; then its scroll bar moves."""

        before = a11y.position(bar)[0]
        self.browser.scroll(*a11y.center(pane), down)
        self.wait_for(
            lambda: a11y.position(bar)[0] != before, "the list scrolls"
        )

    def wait_for(self, get, what, timeout=TIMEOUT):
        """What get returns once it is true; AssertionError after timeout."""

        return a11y.wait_for(get, what, timeout)

    def describe(self) -> str:
        """The widgets that show, one a line."""

        return "\n".join(a11y.describe(self.app)) if self.app else ""

    # The processes

    def children(self):
        """The pids of the processes that Virtualbricks started and run."""

        pids = set()
        for pid in _pids():
            try:
                with open(f"/proc/{pid}/stat") as file:
                    stat = file.read()
            except OSError:
                continue
            # after the name, which is in brackets and may have spaces
            state, ppid = stat[stat.rindex(")") + 2 :].split()[:2]
            if int(ppid) == self.process.pid and state != "Z":
                pids.add(pid)
        return pids

    def bricks(self, name=None):
        """
        The processes whose sockets are in the run folder of the tests:
        bricks of this Virtualbricks, or left by another. With name, those
        of that brick only: its sockets are name.ctl, name.mgmt.
        """

        folder = os.path.join(
            self.desktop.runtime, "virtualbricks", ""
        ).encode()
        pids = []
        for pid in _pids():
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as file:
                    words = file.read().split(b"\0")
            except OSError:
                continue
            sockets = [word for word in words if word.startswith(folder)]
            if name is not None:
                sockets = [
                    word
                    for word in sockets
                    if os.path.basename(word).rpartition(b".")[0]
                    == name.encode()
                ]
            if sockets:
                pids.append(pid)
        return pids


def _pids():
    return [int(name) for name in os.listdir("/proc") if name.isdigit()]


def _spawn(log, env, *args, stdout=None):
    with open(log, "wb") as out:
        return subprocess.Popen(
            args,
            env=env,
            stdout=out if stdout is None else stdout,
            stderr=out,
        )


def _stop(process, timeout=10):
    """Terminate process, if it still runs; kill it after timeout."""

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
