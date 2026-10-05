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
reaches the desktop, nor a Virtualbricks that runs there: not even its
lock, which the Virtualbricks of the tests take in their own folder.
"""

import glob
import os
import re
import shutil
import signal
import socket
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
# Virtualbricks, as python -m virtualbricks, with the system lock of
# --lock system, user and workspace in the folder of the tests: /tmp has the
# one of the Virtualbricks of the user, which it shares with no other.
LAUNCH = (
    "import os, runpy\n"
    "from virtualbricks import locations\n"
    "locations.SYSTEM_LOCK_FILE = os.environ['E2E_SYSTEM_LOCK']\n"
    "runpy.run_module('virtualbricks', run_name='__main__', alter_sys=True)\n"
)
# The options of Virtualbricks that talk to another one, which runs: they
# take none of those of a run, as --lock and --noterm.
CLIENT = ("--command", "--connect")
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
        # the system lock of their Virtualbricks
        self.lock = os.path.join(self.runtime, "virtualbricks.lock")

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
    """
    A Virtualbricks of this checkout, on the screen of the tests: in home,
    its files, as output.log, in folder.
    """

    def __init__(self, desktop, home, folder=None):
        self.desktop = desktop
        self.screen = None
        self.browser = None
        # those of all its screens, the last the browser
        self.browsers = []
        self.home = home
        self.folder = folder or home
        self.config = os.path.join(home, ".config")
        # without it, the start is the first, as after Virtualbricks 2.1
        self.settings = os.path.join(
            self.config, "virtualbricks", "settings.toml"
        )
        self.workspace = os.path.join(home, "workspace")
        self.log = os.path.join(self.folder, "output.log")
        self.process = None
        self.app = None
        # the Virtualbricks that runs the bricks it shows: another one, for
        # the windows of --connect
        self.lab = self
        # the programs it doesn't find, as if this computer hadn't them
        self.hidden = set()

    def make_home(self):
        """Its first settings, those of GTK, and its workspace."""

        for folder, name, text in (
            ("virtualbricks", "settings.toml", SETTINGS),
            ("gtk-3.0", "settings.ini", GTK_SETTINGS),
        ):
            os.makedirs(os.path.join(self.config, folder))
            with open(os.path.join(self.config, folder, name), "w") as file:
                file.write(text)
        os.makedirs(self.workspace)

    def beside(self, folder):
        """
        Another Virtualbricks of the same user: the same home, settings and
        workspace; its files in folder.
        """

        os.makedirs(folder, exist_ok=True)
        other = Virtualbricks(self.desktop, self.home, folder)
        other.workspace = self.workspace
        return other

    def start(self, *options):
        """
        Start Virtualbricks with the options of a scenario, and wait for its
        main window; with --no-gui, until it listens on the socket of
        --listen of its workspace. Once it has quit, it starts again on a
        screen of its own, and its output goes on in the same log.
        """

        if "--no-gui" in options and not _listens_alone(options):
            raise ValueError(
                "without the windows, --listen alone says it runs"
            )
        self.launch(*options)
        if "--no-gui" not in options:
            # only this process: AT-SPI shows the other applications of the
            # bus
            self.app = self.wait_for(
                lambda: a11y.application(self.process.pid),
                "Virtualbricks is on the accessibility bus",
                START_TIMEOUT,
            )
            self.find("frame", timeout=START_TIMEOUT)
        if _listens_alone(options):
            # once its project is open
            self.wait_for(
                self.listens,
                "Virtualbricks listens on the socket of its workspace",
                START_TIMEOUT,
            )

    def launch(self, *options):
        """
        Start Virtualbricks with options, without waiting for it: with the
        windows, on a screen of its own.
        """

        if self.screen is not None:
            self.screen.close()
            self.screen = self.browser = None
        if "--no-gui" not in options:
            self.screen = self.desktop.screen(
                os.path.join(self.folder, "broadway.log")
            )
            self.browser = self.screen.browser
            self.browsers.append(self.browser)
        self.app = None
        with open(self.log, "ab") as out:
            self.process = subprocess.Popen(
                self.arguments(options),
                env=self.environment(),
                cwd=ROOT,
                stdout=out,
                stderr=subprocess.STDOUT,
            )

    def run(self, *options):
        """
        Run Virtualbricks with options, as --command, until it exits: its
        exit status, and its output and its errors, as text.
        """

        return subprocess.run(
            self.arguments(options),
            env=self.environment(),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=QUIT_TIMEOUT,
        )

    def arguments(self, options):
        """
        Its command line, with options: those of the tests first, its
        workspace and no terminal, and no lock unless options name one; a
        Virtualbricks that talks to another, with --command or --connect,
        has only the workspace.
        """

        words = [sys.executable, "-c", LAUNCH]
        if not any(option in CLIENT for option in options):
            words.append("--noterm")
            if not any(option.startswith("--lock") for option in options):
                words += ["--lock", "none"]
        # the words of --command come last
        return words + ["--workspace", self.workspace, *options]

    def environment(self):
        """That of the desktop of the tests, its home and its screen."""

        env = dict(
            self.desktop.env,
            HOME=self.home,
            XDG_CONFIG_HOME=self.config,
            XDG_STATE_HOME=os.path.join(self.home, ".local", "state"),
            XDG_DATA_HOME=os.path.join(self.home, ".local", "share"),
            XDG_CACHE_HOME=os.path.join(self.home, ".cache"),
            E2E_SYSTEM_LOCK=self.desktop.lock,
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
        if self.screen is not None:
            env.update(
                GDK_BACKEND="broadway", BROADWAY_DISPLAY=self.screen.display
            )
        if self.hidden:
            env["PATH"] = self.path_without(env.get("PATH", ""))
        return env

    def path_without(self, path):
        """
        A PATH of one folder of its own, with a link to each program of the
        folders of path, the first of a name, but those hidden.
        """

        folder = os.path.join(self.folder, "path")
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder)
        for directory in filter(None, path.split(os.pathsep)):
            try:
                names = os.listdir(directory)
            except OSError:
                continue
            for name in names:
                program = os.path.join(directory, name)
                link = os.path.join(folder, name)
                if (
                    name in self.hidden
                    or os.path.lexists(link)
                    or os.path.isdir(program)
                    or not os.access(program, os.X_OK)
                ):
                    continue
                os.symlink(program, link)
        return folder

    def control_socket(self):
        """
        The socket of --listen alone of its workspace, in the runtime folder
        of the workspace, which .workspace links to it; None if there is no
        such folder yet.
        """

        runtime = os.path.join(self.desktop.runtime, "virtualbricks")
        workspace = os.path.realpath(self.workspace)
        for link in glob.glob(os.path.join(runtime, "*", ".workspace")):
            if os.path.realpath(link) == workspace:
                return os.path.join(os.path.dirname(link), ".control")
        return None

    def listens(self) -> bool:
        """Whether a Virtualbricks takes a connection on that socket."""

        path = self.control_socket()
        if path is None:
            return False
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            try:
                client.connect(path)
            except OSError:
                return False
        return True

    def stop(self, bricks=True):
        """
        Stop Virtualbricks, if it still runs, and its screen; with bricks,
        all the bricks that are left, also another one's.
        """

        if self.process is not None:
            _stop(self.process, QUIT_TIMEOUT)
            for pid in self.bricks() if bricks else ():
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

    def disabled(self, role, name=None, within=None):
        """The widget, once it shows and is disabled."""

        widget = self.find(role, name, within)
        self.wait_for(
            lambda: not a11y.sensitive(widget),
            f"the {role} {name!r} is disabled",
        )
        return widget

    def click(self, role, name=None, within=None, enabled=True):
        """
        Click in the middle of the widget, once it shows, and is enabled if
        enabled: a user may click a disabled one too.
        """

        if enabled:
            widget = self.enabled(role, name, within)
        else:
            widget = self.find(role, name, within)
        self.browser.click(*a11y.center(widget))
        return widget

    def click_text(self, widget, index, length):
        """
        Click the middle of length characters of the text of the widget,
        from the character index of a11y.text(): a link or a toggle of a text
        view, as a user clicks it. They must show in the widget.
        """

        start = a11y.offset(widget, index)
        x, y, width, height = a11y.text_extents(widget, start, start + length)
        point = (x + width // 2, y + height // 2)
        left, top, room, tall = a11y.extents(widget)
        assert (
            left <= point[0] < left + room and top <= point[1] < top + tall
        ), f"{a11y.text(widget)[index:index + length]!r} doesn't show"
        self.browser.click(*point)

    def spin(self, name, by, within=None):
        """
        Click the + of the spin button name by times, or its - -by times,
        once it shows and is enabled; after each click, its value changes.
        GTK 3 draws - and + at its right end, + last, each about as wide as
        the spin button is high.
        """

        widget = self.enabled("spin button", name, within)
        x, y, width, height = a11y.extents(widget)
        # the middle of +, or of - before it
        button = x + width - height // 2 - (0 if by > 0 else height)
        for _ in range(abs(by)):
            before = a11y.position(widget)[0]
            self.browser.click(button, y + height // 2)
            self.wait_for(
                lambda: a11y.position(widget)[0] != before,
                f"the spin button {name!r} changes",
            )
        return widget

    def type(self, text, role, name=None, within=None, over=False):
        """
        Click the widget, once it shows and is enabled, and type text at its
        cursor; then the widget has it. With over, in place of the text it
        has, as a user who selects it all first: then it has text alone.

        The text goes in through AT-SPI, not as keys: GTK's Broadway backend
        leaves unset the modifiers that a key consumes, which GTK reads
        anyway (_gtk_key_hash_lookup), so a key sometimes matches an
        accelerator or a mnemonic, as a "p" Ctrl+P and a "b" the Alt+B of
        the tab Bricks.

        A spin button is clicked in its text, left of its - and +: the
        middle of it is its -. A password text tells a dot for each of its
        characters, as it shows them: then it has as many more.
        """

        if role == "spin button":
            widget = self.enabled(role, name, within)
            x, y, width, height = a11y.extents(widget)
            # as spin() reckons - and +
            self.browser.click(x + (width - 2 * height) // 2, y + height // 2)
        else:
            widget = self.click(role, name, within)
        if over:
            a11y.erase(widget)
        before = len(a11y.text(widget))
        a11y.write(widget, text)
        what = f"the {role}" if name is None else f"the {role} {name!r}"

        def has():
            shown = a11y.text(widget)
            if role == "password text":
                return len(shown) == before + len(text)
            return shown == text if over else text in shown

        self.wait_for(has, f"{what} has {text!r}")
        return widget

    def drag(self, start, end, ready=None):
        """
        Press at start, a point of the screen, move to end and release
        there, as a user drags. ready(), if given, comes right before the
        press, half a second after the click before: what it did shows.
        """

        self.browser.drag(start, end, ready=ready)

    def key(self, keys, window):
        """
        Press keys, as "Escape", "Return" or "Control+l", in window, a frame
        or a dialog, once it is active: the window clicked last.

        broadwayd gives a key to the window that has the focus when the key
        comes, and gives it to the window pressed only once it has handled
        the press, later: a key right after a click went to the window
        before. GTK makes the window active once broadwayd tells it.

        A key alone, not text: GTK's Broadway backend leaves unset the
        modifiers that a key consumes, which GTK reads anyway, so a key may
        match an accelerator of its character with another modifier, as a
        "p" Ctrl+P; type() writes text.
        """

        self.wait_for(
            lambda: a11y.active(window),
            f"the {window.get_role_name()} {window.get_name()!r} is active",
        )
        self.browser.key(keys)

    def choose(self, item, menu):
        """
        Click the menu of the menu bar, then its item, once it is under the
        menu: GTK may show the menu at the top left of the screen first, and
        move it under the menu bar after, later when the computer is busy.
        """

        title = self.click("menu", menu)
        _x, top, _width, height = a11y.extents(title)
        widget = self.enabled("menu item", item)
        self.wait_for(
            lambda: a11y.extents(widget)[1] >= top + height,
            f"the menu item {item!r} is under the menu {menu!r}",
        )
        self.browser.click(*a11y.center(widget))

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

    def timeline(self):
        """That of its screens, one after the other: see :mod:`broadway`."""

        return [
            event for browser in self.browsers for event in browser.timeline
        ]

    def describe(self) -> str:
        """The widgets that show, one a line."""

        return "\n".join(a11y.describe(self.app)) if self.app else ""

    # The processes

    def children(self, parent=None):
        """
        The pids of the processes that Virtualbricks, or the process parent,
        started and run: for the windows of another, those of the other.
        """

        if parent is None:
            parent = self.lab.process.pid
        pids = set()
        for pid in _pids():
            try:
                with open(f"/proc/{pid}/stat") as file:
                    stat = file.read()
            except OSError:
                continue
            # after the name, which is in brackets and may have spaces
            state, ppid = stat[stat.rindex(")") + 2 :].split()[:2]
            if int(ppid) == parent and state != "Z":
                pids.add(pid)
        return pids

    def bricks(self, name=None):
        """
        The processes whose sockets are in the run folder of the tests:
        bricks of this Virtualbricks, or left by another. With name, those
        of that brick only: its sockets are name.ctl, name.mgmt. A socket is
        a word of the command line, or in one, as QEMU has them:
        ``socket,id=mon,path=PATH,server=on``, ``vde,sock=PATH``.
        """

        folder = os.path.join(self.desktop.runtime, "virtualbricks", "")
        # a path, up to the comma of the next option
        path = re.compile(re.escape(folder) + "[^,]*")
        pids = []
        for pid in _pids():
            words = self.command_line(pid)
            sockets = [found for word in words for found in path.findall(word)]
            if name is not None:
                sockets = [
                    word
                    for word in sockets
                    if os.path.basename(word).rpartition(".")[0] == name
                ]
            if sockets:
                pids.append(pid)
        return pids

    def command_line(self, pid):
        """The words of the command line of the process pid; none once gone."""

        try:
            with open(f"/proc/{pid}/cmdline", "rb") as file:
                words = file.read().split(b"\0")
        except OSError:
            return []
        # after the last word, a \0 too
        return [os.fsdecode(word) for word in words[:-1]]


def _listens_alone(options):
    """Whether options have --listen alone: the socket of the workspace."""

    for i, option in enumerate(options):
        if option == "--listen":
            following = options[i + 1 : i + 2]
            if not following or following[0].startswith("-"):
                return True
    return False


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
