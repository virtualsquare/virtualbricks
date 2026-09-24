# -*- test-case-name: virtualbricks.tests.migrate.test_cli -*-
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
The command line of the migration: ``python -m virtualbricks.migrate``.

With ``--gui``, or as ``virtualbricks-migrate``, it opens the migration window
instead, filled with the folders and the settings file given.
"""

import argparse
import os
import sys

from virtualbricks.migrate import engine

DESCRIPTION = """\
Convert the settings and projects of Virtualbricks 2.1 and older to the new
format. The old files are only read. Give an old workspace and a new or empty
folder to try it out, or --in-place to migrate your files. With --gui, the
migration window opens, filled with what is given."""

EPILOG = """\
exit status: 0 if every project was migrated (warnings are fine), 1 if one
failed, 2 for bad arguments, 3 if Virtualbricks is running and the files are
to be migrated in place."""

RUNNING = "Virtualbricks is running: close it to migrate your files in place"
EXIT_RUNNING = 3
# The options that the window doesn't have.
NOT_IN_THE_WINDOW = (
    ("copy_files", "--copy-files"),
    ("dry_run", "--dry-run"),
    ("verbose", "--verbose"),
)


def parser(prog="python -m virtualbricks.migrate"):
    parser = argparse.ArgumentParser(
        prog=prog,
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "folders",
        nargs="*",
        metavar="INPUT OUTPUT",
        help="an old workspace, and the folder to write the result to",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="open the migration window",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="migrate your files, next to the old ones",
    )
    parser.add_argument(
        "--settings",
        metavar="FILE",
        help="an old settings file to migrate too",
    )
    parser.add_argument(
        "--copy-files",
        action="store_true",
        help="also copy the disks and other files of each project",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="convert and check everything, but write nothing",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="also print the informational messages",
    )
    return parser


def make_migration(args, error):
    options = {"dry_run": args.dry_run, "verbose": args.verbose}
    if args.in_place:
        if args.folders:
            error("--in-place takes no folders")
        if args.copy_files:
            error("--copy-files is for migrating to a folder")
        return engine.in_place_migration(args.settings, **options)
    if len(args.folders) != 2:
        error("give an input and an output folder, --in-place or --gui")
    source, output = args.folders
    if not os.path.isdir(source):
        error(f"{source} is not a folder")
    if os.path.exists(output) and (
        not os.path.isdir(output) or os.listdir(output)
    ):
        error(f"{output} must be a new or empty folder")
    if args.settings is not None and not os.path.isfile(args.settings):
        error(f"{args.settings} is not a file")
    return engine.Migration(
        source,
        engine.Folder(output),
        args.settings,
        copy_files=args.copy_files,
        **options,
    )


def window_options(args, error):
    """Return what fills the window; the window checks it before running."""

    for name, option in NOT_IN_THE_WINDOW:
        if getattr(args, name):
            error(f"{option} is not available in the window")
    if len(args.folders) > 2:
        error("give at most an input and an output folder")
    if args.in_place and len(args.folders) > 1:
        error("--in-place takes no output folder")
    folders = args.folders + [None] * (2 - len(args.folders))
    return {
        "workspace": folders[0],
        "settings_file": args.settings,
        "output": folders[1],
        "in_place": args.in_place,
    }


def open_window(**options):  # pragma: no cover (it installs the GTK reactor)
    from virtualbricks.migrate import gui

    gui.main(**options)
    return 0


def main(argv=None, stdout=None, prog="python -m virtualbricks.migrate"):
    stdout = stdout or sys.stdout
    arguments = parser(prog)
    args = arguments.parse_args(argv)
    if args.gui:
        return open_window(**window_options(args, arguments.error))
    migration = make_migration(args, arguments.error)
    lock = None
    if isinstance(migration.target, engine.InPlace) and not args.dry_run:
        lock = engine.lock_in_place()
        if lock is None:
            arguments.exit(EXIT_RUNNING, f"{arguments.prog}: {RUNNING}\n")
    try:
        migration.run()
    finally:
        if lock is not None:
            lock.unlock()
    stdout.write(migration.text())
    if not args.dry_run:
        stdout.write(f"Report: {migration.target.report_file}\n")
    return migration.exit_code


def gui_main(argv=None):
    """The ``virtualbricks-migrate`` command: the window, filled with argv."""

    if argv is None:
        argv = sys.argv[1:]
    return main(["--gui"] + list(argv), prog="virtualbricks-migrate")
