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

import io
import os
import sys

from twisted.trial import unittest

from virtualbricks import locations
from virtualbricks.config import load_toml
from virtualbricks.migrate import (
    EXIT_RUNNING,
    REPORT_FILE,
    RUNNING,
    Migration,
    cli,
    main,
)
from virtualbricks.tests import (
    hold_lock,
    isolate,
    lock_is_free,
    reset_settings,
)
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    write,
    write_project,
    write_settings,
)


class TestCommandLine(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.workspace = os.path.join(self.root, "old")
        self.output = os.path.join(self.root, "new")
        write_project(self.workspace, "lab", CONFIG1)
        self.stderr = io.StringIO()
        self.patch(sys, "stderr", self.stderr)

    def main(self, *argv):
        stdout = io.StringIO()
        code = main(list(argv), stdout)
        return code, stdout.getvalue()

    def error(self, *argv):
        exc = self.assertRaises(SystemExit, main, list(argv), io.StringIO())
        self.assertEqual(exc.code, 2)
        return self.stderr.getvalue().splitlines()[-1]

    def test_migrate_to_a_folder(self):
        code, out = self.main(self.workspace, self.output)
        self.assertEqual(code, 0)
        report_file = os.path.join(self.output, REPORT_FILE)
        self.assertEqual(
            out.splitlines(),
            [
                "lab       migrated   1 warning",
                "",
                "lab",
                "  warning   .project:2  [Image:martin] /vimages/vtatpa.martin.qcow2 "
                "not found, kept in the library",
                "",
                "1 of 1 projects migrated.",
                f"Report: {report_file}",
            ],
        )
        path = os.path.join(
            self.output, "workspace", "lab", locations.PROJECT_FILE
        )
        self.assertIn("sender", load_toml(path)["bricks"])

    def test_empty_output_folder(self):
        os.makedirs(self.output)
        self.assertEqual(self.main(self.workspace, self.output)[0], 0)

    def test_settings_and_verbose(self):
        old = write_settings(
            os.path.join(self.root, "vb.conf"), "/srv/vb", "lab"
        )
        code, out = self.main(
            "-v", "--settings", old, self.workspace, self.output
        )
        self.assertEqual(code, 0)
        self.assertIn("vb.conf   migrated", out)
        self.assertIn("[Wirefilter:wf] became netemu", out)
        settings_file = os.path.join(
            self.output, "config", "virtualbricks", "settings.toml"
        )
        self.assertEqual(
            load_toml(settings_file)["workspace"],
            os.path.join(self.output, "workspace"),
        )

    def test_copy_files(self):
        write(os.path.join(self.workspace, "lab", "disk.qcow2"), "")
        self.main("--copy-files", self.workspace, self.output)
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.output, "workspace", "lab", "disk.qcow2")
            )
        )

    def test_dry_run(self):
        code, out = self.main("--dry-run", self.workspace, self.output)
        self.assertEqual(code, 0)
        self.assertNotIn("Report:", out)
        self.assertFalse(os.path.exists(self.output))

    def test_failure(self):
        write_project(self.workspace, "bad", "[Tap:t]\n[Tap:t]\n")
        code, out = self.main(self.workspace, self.output)
        self.assertEqual(code, 1)
        self.assertIn("1 of 2 projects migrated, 1 failed.", out)

    def test_in_place(self):
        home_workspace = os.path.join(self.root, ".virtualbricks")
        write_project(home_workspace, "mine", CONFIG1)
        code, out = self.main("--in-place")
        self.assertEqual(code, 0)
        self.assertTrue(
            os.path.isfile(
                os.path.join(home_workspace, "mine", locations.PROJECT_FILE)
            )
        )
        report_file = os.path.join(
            self.root, ".local", "state", "virtualbricks", REPORT_FILE
        )
        self.assertTrue(out.endswith(f"Report: {report_file}\n"))

    def test_in_place_holds_the_lock(self):
        home_workspace = os.path.join(self.root, ".virtualbricks")
        write_project(home_workspace, "mine", CONFIG1)
        held = []
        run = Migration.run

        def spy(migration):
            held.append(not lock_is_free())
            return run(migration)

        self.patch(Migration, "run", spy)
        self.assertEqual(self.main("--in-place")[0], 0)
        # locked while running, free again after
        self.assertEqual(held, [True])
        self.assertTrue(lock_is_free())

    def test_in_place_releases_the_lock_on_errors(self):
        def fail(migration):
            raise RuntimeError("broken")

        self.patch(Migration, "run", fail)
        self.assertRaises(RuntimeError, self.main, "--in-place")
        self.assertTrue(lock_is_free())

    def test_in_place_while_virtualbricks_runs(self):
        home_workspace = os.path.join(self.root, ".virtualbricks")
        write_project(home_workspace, "mine", CONFIG1)
        hold_lock(self)
        exc = self.assertRaises(SystemExit, self.main, "--in-place")
        self.assertEqual(exc.code, EXIT_RUNNING)
        self.assertEqual(
            self.stderr.getvalue(),
            f"python -m virtualbricks.migrate: {RUNNING}\n",
        )
        self.assertFalse(
            os.path.exists(
                os.path.join(home_workspace, "mine", locations.PROJECT_FILE)
            )
        )
        # a dry run writes nothing and needs no lock
        self.assertEqual(self.main("--in-place", "--dry-run")[0], 0)
        # nor does a migration to a folder
        self.assertEqual(self.main(self.workspace, self.output)[0], 0)

    def test_in_place_with_settings(self):
        old = write_settings(
            os.path.join(self.root, "vb.conf"), self.workspace, "lab"
        )
        code, out = self.main("--in-place", "--settings", old)
        self.assertEqual(code, 0)
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.workspace, "lab", locations.PROJECT_FILE)
            )
        )
        self.assertEqual(
            load_toml(locations.settings_file())["workspace"],
            self.workspace,
        )

    def test_bad_arguments(self):
        cases = [
            ((), "give an input and an output folder, --in-place or --gui"),
            (
                (self.workspace,),
                "give an input and an output folder, --in-place or --gui",
            ),
            (("--in-place", self.workspace), "--in-place takes no folders"),
            (
                ("--in-place", "--copy-files"),
                "--copy-files is for migrating to a folder",
            ),
            ((self.output, self.root), f"{self.output} is not a folder"),
            (
                (self.workspace, self.root),
                f"{self.root} must be a new or empty folder",
            ),
            (
                (
                    "--settings",
                    os.path.join(self.root, "missing.conf"),
                    self.workspace,
                    self.output,
                ),
                f"{os.path.join(self.root, 'missing.conf')} is not a file",
            ),
        ]
        for argv, message in cases:
            self.assertTrue(
                self.error(*argv).endswith(f"error: {message}"), argv
            )

    def test_output_is_a_file(self):
        path = write(os.path.join(self.root, "file"), "")
        self.assertIn(
            "must be a new or empty folder", self.error(self.workspace, path)
        )

    def test_help(self):
        stdout = io.StringIO()
        self.patch(sys, "stdout", stdout)
        exc = self.assertRaises(SystemExit, main, ["--help"])
        self.assertEqual(exc.code, 0)
        text = stdout.getvalue()
        self.assertIn("python -m virtualbricks.migrate", text)
        self.assertIn("exit status:", text)

    def test_default_stdout(self):
        stdout = io.StringIO()
        self.patch(sys, "stdout", stdout)
        self.assertEqual(main([self.workspace, self.output]), 0)
        self.assertIn("1 of 1 projects migrated.", stdout.getvalue())


class TestWindow(unittest.TestCase):

    def setUp(self):
        self.opened = []
        self.patch(cli, "open_window", self.open_window)
        self.stderr = io.StringIO()
        self.patch(sys, "stderr", self.stderr)

    def open_window(self, **options):
        self.opened.append(options)
        return 0

    def test_empty_window(self):
        self.assertEqual(main(["--gui"]), 0)
        self.assertEqual(
            self.opened,
            [
                {
                    "workspace": None,
                    "settings_file": None,
                    "output": None,
                    "in_place": False,
                }
            ],
        )

    def test_filled_window(self):
        main(["--gui", "--settings", "/vb.conf", "/old", "/new"])
        self.assertEqual(
            self.opened[0],
            {
                "workspace": "/old",
                "settings_file": "/vb.conf",
                "output": "/new",
                "in_place": False,
            },
        )
        main(["--gui", "--in-place", "/old"])
        self.assertEqual(
            self.opened[1],
            {
                "workspace": "/old",
                "settings_file": None,
                "output": None,
                "in_place": True,
            },
        )

    def test_folders_are_checked_by_the_window(self):
        main(["--gui", "/does/not/exist"])
        self.assertEqual(self.opened[0]["workspace"], "/does/not/exist")

    def test_options_of_the_command_line_only(self):
        cases = [
            (["--copy-files"], "--copy-files is not available in the window"),
            (["--dry-run"], "--dry-run is not available in the window"),
            (["-v"], "--verbose is not available in the window"),
            (["a", "b", "c"], "give at most an input and an output folder"),
            (["--in-place", "a", "b"], "--in-place takes no output folder"),
        ]
        for argv, message in cases:
            exc = self.assertRaises(
                SystemExit, main, ["--gui"] + argv, io.StringIO()
            )
            self.assertEqual(exc.code, 2)
            last = self.stderr.getvalue().splitlines()[-1]
            self.assertTrue(last.endswith(f"error: {message}"), argv)
        self.assertEqual(self.opened, [])

    def test_gui_main(self):
        self.assertEqual(cli.gui_main(["/old"]), 0)
        self.assertEqual(self.opened[0]["workspace"], "/old")
        self.patch(sys, "argv", ["virtualbricks-migrate", "--in-place"])
        cli.gui_main()
        self.assertTrue(self.opened[1]["in_place"])

    def test_gui_main_usage(self):
        exc = self.assertRaises(SystemExit, cli.gui_main, ["--dry-run"])
        self.assertEqual(exc.code, 2)
        self.assertTrue(
            self.stderr.getvalue().startswith("usage: virtualbricks-migrate")
        )
