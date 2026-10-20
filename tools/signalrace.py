#!/usr/bin/env python3
# -*- test-case-name: virtualbricks.tests.test_tools -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team
#
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
Two signals against a Virtualbricks that runs, many times: how often it hangs.

    python tools/signalrace.py                     300 runs, two SIGTERMs
    python tools/signalrace.py --signals SIGTERM SIGINT --between 0 1000
    python tools/signalrace.py --stdout            -l - instead of a file
    python tools/signalrace.py --python VENV/bin/python

Each run starts virtualbricks --no-gui --no-term --lock none -l FILE of this
checkout, in a home of its own and without a lock, which another Virtualbricks
of the computer would hold. It waits until the process catches SIGTERM: the
reactor runs, with its handlers. Half a second later it sends the first
signal, and the second after a delay drawn between the two numbers of
--between, in microseconds. A run still there 3 s later hung.

The handlers of the reactor once logged from inside the signal handler, and a
signal that came in the middle of a write to the log file waited forever for
the lock of its own thread: two signals 200 to 400 microseconds apart hung
about 1.5% of the runs, on Twisted 26.4 and 22.1 (fixed in 19110580). The
folders of the runs that hang stay, with their log; the others go.
"""

import argparse
import os
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SIGNALS = ("SIGTERM", "SIGINT")


class Hung(NamedTuple):
    """A run still there after its two signals."""

    # between the two signals, as measured, in microseconds
    delay: float
    folder: str


class DidNotStart(Exception):
    """The program ended, or didn't catch SIGTERM in time."""


def command(python: str, folder: str, stdout: bool) -> list[str]:
    """Virtualbricks without the windows, the console or a lock, in folder."""

    log = "-" if stdout else os.path.join(folder, "vb.log")
    return [
        python,
        "-m",
        "virtualbricks",
        "--no-gui",
        "--no-term",
        # the system lock, in /tmp, is that of every Virtualbricks of the
        # computer, which --workspace would share
        "--lock",
        "none",
        "--workspace",
        os.path.join(folder, "workspace"),
        "-l",
        log,
    ]


def catches_sigterm(pid: int) -> bool:
    """If the process has a handler of SIGTERM, as /proc says."""

    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("SigCgt:"):
                    caught = int(line.split()[1], 16)
                    return bool(caught >> (signal.SIGTERM - 1) & 1)
    except OSError:
        # it's gone: the caller sees that it ended
        pass
    return False


def wait_for_handlers(
    process: subprocess.Popen[bytes], timeout: float
) -> None:
    """Until the process catches SIGTERM; DidNotStart if it doesn't."""

    end = time.monotonic() + timeout
    while not catches_sigterm(process.pid):
        if process.poll() is not None:
            raise DidNotStart(f"it ended with {process.returncode}")
        if time.monotonic() > end:
            raise DidNotStart(f"it didn't catch SIGTERM in {timeout:g} s")
        time.sleep(0.05)


def one_run(
    argv: Sequence[str],
    folder: str,
    signals: Sequence[signal.Signals],
    between: Sequence[float],
    settle: float = 0.5,
    wait: float = 3.0,
    start: float = 30.0,
) -> Hung | None:
    """Run argv in folder, its home, send it the two signals: if it hung."""

    runtime = os.path.join(folder, "run")
    os.makedirs(runtime)
    env = dict(
        os.environ,
        HOME=folder,
        XDG_CONFIG_HOME=os.path.join(folder, ".config"),
        XDG_DATA_HOME=os.path.join(folder, ".local", "share"),
        XDG_RUNTIME_DIR=runtime,
    )
    with (
        open(os.path.join(folder, "stdout"), "wb") as stdout,
        open(os.path.join(folder, "stderr"), "wb") as stderr,
    ):
        process = subprocess.Popen(
            argv,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )
    try:
        wait_for_handlers(process, start)
        time.sleep(settle)
        first, second = signals
        delay = random.uniform(*between) / 1e6
        sent = time.perf_counter()
        os.kill(process.pid, first)
        while time.perf_counter() < sent + delay:
            pass
        os.kill(process.pid, second)
        measured = (time.perf_counter() - sent) * 1e6
        try:
            process.wait(wait)
        except subprocess.TimeoutExpired:
            return Hung(measured, folder)
        return None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def last_lines(path: str, count: int = 5) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as file:
            return file.read().rstrip().splitlines()[-count:]
    except OSError:
        return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Two signals against a Virtualbricks that runs, many"
        " times: how often it hangs."
    )
    parser.add_argument(
        "--runs", type=int, default=300, help="how many (default: 300)"
    )
    parser.add_argument(
        "--between",
        type=float,
        nargs=2,
        default=(200.0, 400.0),
        metavar=("MIN", "MAX"),
        help="microseconds between the signals (default: 200 400)",
    )
    parser.add_argument(
        "--signals",
        nargs=2,
        choices=SIGNALS,
        default=("SIGTERM", "SIGTERM"),
        metavar="SIGNAL",
        help="the first and the second, SIGTERM or SIGINT"
        " (default: SIGTERM SIGTERM)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="log to the standard output, -l -, instead of a file",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="the Python that runs Virtualbricks (default: this one)",
    )
    parser.add_argument(
        "--jobs", type=int, default=8, help="runs at once (default: 8)"
    )
    args = parser.parse_args(argv)
    signals = [signal.Signals[name] for name in args.signals]
    root = tempfile.mkdtemp(prefix="signalrace.")
    # once a run didn't start, the others don't either
    failed: list[tuple[str, DidNotStart]] = []
    stop = threading.Event()

    def run(number: int) -> Hung | None:
        if stop.is_set():
            return None
        folder = os.path.join(root, str(number))
        os.makedirs(folder)
        argv = command(args.python, folder, args.stdout)
        try:
            hung = one_run(argv, folder, signals, args.between)
        except DidNotStart as exc:
            failed.append((folder, exc))
            stop.set()
            return None
        if hung is None:
            shutil.rmtree(folder)
        return hung

    with ThreadPoolExecutor(args.jobs) as pool:
        hung = [each for each in pool.map(run, range(args.runs)) if each]
    if failed:
        folder, exc = failed[0]
        print(f"A run didn't start: {exc}. Its folder: {folder}")
        for line in last_lines(os.path.join(folder, "stderr")):
            print(f"  {line}")
        return 2
    low, high = args.between
    print(
        f"{len(hung)} of {args.runs} runs hung"
        f" ({' '.join(args.signals)}, {low:g}-{high:g} µs apart)"
    )
    for each in hung:
        print(f"  {each.delay:.0f} µs: {each.folder}")
    if not hung:
        os.rmdir(root)
    return 1 if hung else 0


if __name__ == "__main__":
    sys.exit(main())
