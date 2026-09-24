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

import errno
import os

from twisted.python import lockfile
from twisted.trial import unittest

from virtualbricks import locations
from virtualbricks.config import settings, tomlfile
from virtualbricks.migrate import engine
from virtualbricks.config.report import Report
from virtualbricks.tests import (
    FakeLogger,
    hold_lock,
    isolate,
    lock_is_free,
    release,
    reset_settings,
)
from virtualbricks.tests.migrate.fixtures import (
    CONFIG1,
    WAN,
    write,
    write_project,
    write_settings,
)


class EngineTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.workspace = os.path.join(self.root, "old")
        self.output = os.path.join(self.root, "new")

    def folder_migration(self, legacy_settings=None, **options):
        return engine.Migration(
            self.workspace,
            engine.Folder(self.output),
            legacy_settings,
            **options,
        )

    def statuses(self, migration):
        return [(item.name, item.status) for item in migration.items]


class TestTargets(EngineTestCase):

    def test_in_place(self):
        target = engine.InPlace(self.workspace)
        self.assertIsNone(target.folder)
        self.assertEqual(target.settings_file, locations.settings_file())
        self.assertEqual(target.state_file, locations.state_file())
        self.assertEqual(
            target.report_file,
            os.path.join(
                self.root,
                ".local",
                "state",
                "virtualbricks",
                engine.REPORT_FILE,
            ),
        )
        self.assertEqual(
            target.project_dir("lab"), os.path.join(self.workspace, "lab")
        )

    def test_folder(self):
        target = engine.Folder(self.output)
        self.assertEqual(
            target.workspace, os.path.join(self.output, "workspace")
        )
        self.assertEqual(
            target.settings_file,
            os.path.join(
                self.output, "config", "virtualbricks", "settings.toml"
            ),
        )
        self.assertEqual(
            target.state_file,
            os.path.join(self.output, "state", "virtualbricks", "state.toml"),
        )
        self.assertEqual(
            target.report_file, os.path.join(self.output, engine.REPORT_FILE)
        )
        self.assertEqual(
            target.project_dir("lab"),
            os.path.join(self.output, "workspace", "lab"),
        )


class TestDiscover(EngineTestCase):

    def test_missing_workspace(self):
        self.assertEqual(engine.discover(self.workspace), [])

    def test_project_source(self):
        directory = os.path.join(self.workspace, "lab")
        os.makedirs(directory)
        self.assertIsNone(engine.project_source(directory))
        path = write_project(self.workspace, "lab")
        self.assertEqual(engine.project_source(directory), path)
        backup = write_project(self.workspace, "lab", filename=".project~")
        self.assertEqual(engine.project_source(directory), backup)

    def test_projects(self):
        write_project(self.workspace, "lab")
        write_project(self.workspace, ".hidden")
        os.makedirs(os.path.join(self.workspace, "vimages"))
        write(os.path.join(self.workspace, "notes.txt"), "hello\n")
        write(os.path.join(self.workspace, ".old.vbl"), CONFIG1)
        write(os.path.join(self.workspace, "single.vbl"), CONFIG1)
        items = engine.discover(self.workspace)
        self.assertEqual(
            [(item.name, item.kind, item.status) for item in items],
            [
                ("lab", "project", engine.WAITING),
                ("single", "file", engine.WAITING),
            ],
        )
        self.assertEqual(
            items[1].source, os.path.join(self.workspace, "single.vbl")
        )
        self.assertTrue(items[0].is_project)

    def test_file_named_after_a_directory(self):
        write_project(self.workspace, "lab")
        os.makedirs(os.path.join(self.workspace, "lab_1"))
        write(os.path.join(self.workspace, "lab.vbl"), CONFIG1)
        names = [item.name for item in engine.discover(self.workspace)]
        self.assertEqual(names, ["lab", "lab_2"])

    def test_file_migrated_in_place_keeps_its_name(self):
        write(os.path.join(self.workspace, "lab.vbl"), CONFIG1)
        write(os.path.join(self.workspace, "lab", locations.PROJECT_FILE), "")
        names = [item.name for item in engine.discover(self.workspace)]
        self.assertEqual(names, ["lab"])


class TestMigrateToFolder(EngineTestCase):

    def setUp(self):
        super().setUp()
        self.legacy_settings = write_settings(
            os.path.join(self.root, "vb.conf"),
            "/home/alice/.virtualbricks",
            "wan",
        )
        write_project(self.workspace, "lab1", CONFIG1)
        write(os.path.join(self.workspace, "lab1", "README"), "My lab\n")
        write(os.path.join(self.workspace, "lab1", "notes", "a.txt"), "a\n")
        write_project(self.workspace, "wan", WAN)

    def test_migrate(self):
        migration = self.folder_migration(self.legacy_settings).run()
        self.assertEqual(
            self.statuses(migration),
            [
                ("vb.conf", engine.MIGRATED),
                ("lab1", engine.MIGRATED),
                ("wan", engine.MIGRATED),
            ],
        )
        self.assertEqual(migration.exit_code, 0)
        target = migration.target
        data = tomlfile.load(target.settings_file)
        self.assertEqual(data["format"], settings.FORMAT)
        self.assertEqual(data["workspace"], target.workspace)
        self.assertEqual(data["cowfmt"], "qcow")
        self.assertEqual(
            tomlfile.load(target.state_file),
            {"format": settings.FORMAT, "current_project": "wan"},
        )
        project = tomlfile.load(
            os.path.join(target.workspace, "lab1", "project.toml")
        )
        self.assertIn("sender", project["bricks"])
        # the per-project settings come from the old settings
        self.assertEqual(project["settings"]["cowfmt"], "qcow")
        self.assertIs(project["settings"]["femaleplugs"], True)
        with open(os.path.join(target.workspace, "lab1", "README")) as fp:
            self.assertEqual(fp.read(), "My lab\n")
        self.assertFalse(
            os.path.exists(os.path.join(target.workspace, "lab1", "notes"))
        )
        with open(target.report_file) as fp:
            self.assertEqual(fp.read(), migration.text())
        self.assertEqual(
            [item.bricks for item in migration.items], [None, 3, 3]
        )
        # the old files are untouched
        self.assertEqual(
            sorted(os.listdir(os.path.join(self.workspace, "lab1"))),
            [".project", "README", "notes"],
        )

    def test_workspace_info(self):
        migration = self.folder_migration(self.legacy_settings).run()
        self.assertIn(
            f"workspace set to {migration.target.workspace}",
            [m.text for m in migration.items[0].report],
        )

    def test_copy_files(self):
        fifo = os.path.join(self.workspace, "lab1", "sw.ctl")
        os.mkfifo(fifo)
        migration = self.folder_migration(copy_files=True).run()
        lab1 = migration.target.project_dir("lab1")
        self.assertEqual(
            sorted(os.listdir(lab1)), ["README", "notes", "project.toml"]
        )
        self.assertEqual(os.listdir(os.path.join(lab1, "notes")), ["a.txt"])

    def test_dry_run(self):
        migration = self.folder_migration(
            self.legacy_settings, dry_run=True
        ).run()
        self.assertEqual(migration.count(engine.MIGRATED), 2)
        self.assertEqual(
            [item.bricks for item in migration.items], [None, 3, 3]
        )
        self.assertFalse(os.path.exists(self.output))

    def test_no_state_without_settings(self):
        migration = self.folder_migration().run()
        self.assertFalse(os.path.exists(migration.target.state_file))
        self.assertFalse(os.path.exists(migration.target.settings_file))
        project = tomlfile.load(
            os.path.join(migration.target.project_dir("lab1"), "project.toml")
        )
        self.assertEqual(project["settings"]["cowfmt"], "qcow2")

    def test_skip_what_is_migrated(self):
        self.folder_migration(self.legacy_settings).run()
        migration = self.folder_migration(self.legacy_settings)
        self.assertEqual(
            self.statuses(migration),
            [
                ("vb.conf", engine.SKIPPED),
                ("lab1", engine.SKIPPED),
                ("wan", engine.SKIPPED),
            ],
        )
        self.assertEqual(migration.pending(), [])
        self.assertEqual(
            [m.text for m in migration.items[0].report],
            [f"{migration.target.settings_file} already exists, skipped"],
        )
        self.assertEqual(
            [m.text for m in migration.items[1].report],
            ["already migrated, skipped"],
        )
        steps = list(migration.steps())
        self.assertEqual(steps, [])

    def test_steps(self):
        migration = self.folder_migration()
        seen = [(item.name, item.status) for item in migration.steps()]
        self.assertEqual(
            seen,
            [
                ("lab1", engine.MIGRATING),
                ("lab1", engine.MIGRATED),
                ("wan", engine.MIGRATING),
                ("wan", engine.MIGRATED),
            ],
        )

    def test_single_file_project(self):
        write(os.path.join(self.workspace, "single.vbl"), CONFIG1)
        migration = self.folder_migration().run()
        single = migration.target.project_dir("single")
        self.assertEqual(os.listdir(single), ["project.toml"])


class TestFailures(EngineTestCase):

    def test_not_a_text_file(self):
        path = write_project(self.workspace, "lab")
        with open(path, "wb") as fp:
            fp.write(b"\xff\xfe[")
        migration = self.folder_migration().run()
        item = migration.items[0]
        self.assertEqual(item.status, engine.FAILED)
        self.assertEqual(
            [m.text for m in item.report],
            ["not a text file (invalid start byte); project not migrated"],
        )
        self.assertEqual(migration.exit_code, 1)
        self.assertFalse(os.path.exists(migration.target.project_dir("lab")))

    def test_unreadable_file(self):
        path = write_project(self.workspace, "lab")
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)
        if os.access(path, os.R_OK):  # pragma: no cover
            raise unittest.SkipTest("running as root")
        item = self.folder_migration().run().items[0]
        self.assertEqual(
            [m.text for m in item.report],
            [f"Permission denied: {path}; not migrated"],
        )

    def test_project_that_cannot_be_represented(self):
        write_project(self.workspace, "lab", "[Switch:sw]\n[Switch:sw]\n")
        write_project(self.workspace, "wan", WAN)
        migration = self.folder_migration().run()
        self.assertEqual(
            self.statuses(migration),
            [("lab", engine.FAILED), ("wan", engine.MIGRATED)],
        )
        self.assertEqual(
            [m.text for m in migration.items[0].report],
            [
                ".project:2 [Switch:sw] defined twice (first at line 1); "
                "project not migrated"
            ],
        )
        self.assertEqual(
            migration.summary(), "1 of 2 projects migrated, 1 failed."
        )

    def test_settings_that_cannot_be_read(self):
        path = write(os.path.join(self.root, "vb.conf"), "term = x\n")
        migration = self.folder_migration(path).run()
        self.assertEqual(
            self.statuses(migration), [("vb.conf", engine.FAILED)]
        )
        self.assertFalse(os.path.exists(migration.target.settings_file))
        self.assertEqual(migration.exit_code, 1)

    def test_interrupted_save(self):
        write_project(self.workspace, "lab", "[Switch:half")
        write_project(self.workspace, "lab", CONFIG1, filename=".project~")
        item = self.folder_migration().run().items[0]
        self.assertEqual(item.status, engine.MIGRATED)
        self.assertIn(
            ".project~, left by an interrupted save, used",
            [m.text for m in item.report],
        )

    def test_describe_error(self):
        self.assertEqual(
            engine._describe_error(OSError("disk full")),
            "disk full; not migrated",
        )
        error = OSError(errno.ENOENT, "No such file", "/x")
        self.assertEqual(
            engine._describe_error(error), "No such file: /x; not migrated"
        )


class TestInPlace(EngineTestCase):

    def test_migrate(self):
        write_project(self.workspace, "lab")
        write(os.path.join(self.workspace, "single.vbl"), CONFIG1)
        migration = engine.Migration(
            self.workspace, engine.InPlace(self.workspace)
        )
        migration.run()
        self.assertTrue(
            os.path.isfile(os.path.join(self.workspace, "lab", "project.toml"))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.workspace, "single", "project.toml")
            )
        )
        self.assertTrue(os.path.isfile(migration.target.report_file))
        again = engine.Migration(
            self.workspace, engine.InPlace(self.workspace)
        )
        self.assertEqual(again.pending(), [])


class TestReporting(EngineTestCase):

    def setUp(self):
        super().setUp()
        write_project(self.workspace, "lab", CONFIG1)
        write_project(
            self.workspace, "a_long_project_name", "[Switch:sw]\nhub=x\n"
        )
        write_project(self.workspace, "bad", "[Tap:t]\n[Tap:t]\n")

    def test_text(self):
        migration = self.folder_migration().run()
        self.assertEqual(
            migration.text(),
            "a_long_project_name  migrated   \n"
            "bad                  failed     1 error\n"
            "lab                  migrated   1 warning\n"
            "\n"
            "bad\n"
            "  error     .project:2 [Tap:t] defined twice (first at line 1); "
            "project not migrated\n"
            "\n"
            "lab\n"
            "  warning   .project:2  [Image:martin] /vimages/vtatpa.martin.qcow2 "
            "not found, kept in the library\n"
            "\n"
            "2 of 3 projects migrated, 1 failed.\n",
        )

    def test_verbose_text(self):
        migration = self.folder_migration(verbose=True).run()
        text = migration.text()
        self.assertIn(
            "  info      .project:12  [Wirefilter:wf] became netemu\n", text
        )

    def test_counts(self):
        item = engine.Item("x", "project", "/x")
        self.assertEqual(engine.counts(item), "")
        item.report.error("a")
        item.report.warning("b")
        item.report.warning("c")
        self.assertEqual(engine.counts(item), "1 error, 2 warnings")

    def test_log(self):
        migration = self.folder_migration(verbose=True).run()
        logger = FakeLogger()
        migration.log(logger)
        lines = logger.formatted()
        self.assertIn(
            "bad: .project:2 [Tap:t] defined twice (first at line 1); project "
            "not migrated",
            lines,
        )
        self.assertIn(
            "lab: .project:2: [Image:martin] /vimages/vtatpa.martin.qcow2 not "
            "found, kept in the library",
            lines,
        )
        self.assertIn("lab: .project:12: [Wirefilter:wf] became netemu", lines)
        self.assertEqual(
            lines[-1], "Migration: 2 of 3 projects migrated, 1 failed."
        )
        self.assertEqual(
            sorted(set(logger.levels())), ["error", "info", "warn"]
        )

    def test_log_does_not_repeat_the_name(self):
        migration = self.folder_migration()
        migration.items[0].report.warning("x", "a_long_project_name/.project")
        logger = FakeLogger()
        migration.log(logger)
        self.assertEqual(
            logger.formatted()[0], "a_long_project_name/.project: x"
        )

    def test_nothing_to_migrate(self):
        migration = engine.Migration(
            self.root + "/none", engine.Folder(self.output)
        )
        self.assertEqual(
            migration.run().text(), "\n0 of 0 projects migrated.\n"
        )


class TestEntryPoints(EngineTestCase):

    def setUp(self):
        super().setUp()
        self.legacy_settings = locations.legacy_settings_file()

    def test_fresh_install(self):
        self.assertIsNone(engine.startup_migration())

    def test_startup_with_old_settings(self):
        write_settings(self.legacy_settings, self.workspace, "lab")
        write_project(self.workspace, "lab")
        migration = engine.startup_migration()
        self.assertEqual(
            [item.name for item in migration.pending()],
            [locations.LEGACY_SETTINGS_FILE, "lab"],
        )
        self.assertIsInstance(migration.target, engine.InPlace)
        self.assertEqual(migration.workspace, self.workspace)
        migration.run()
        self.assertEqual(
            settings.AppSettings().workspace,
            os.path.join(self.root, ".virtualbricks"),
        )
        self.assertEqual(
            tomlfile.load(locations.settings_file())["workspace"],
            self.workspace,
        )
        self.assertEqual(
            tomlfile.load(locations.state_file())["current_project"], "lab"
        )
        self.assertIsNone(engine.startup_migration())

    def test_startup_with_new_settings(self):
        # an old project copied into a migrated workspace
        write(
            locations.settings_file(),
            tomlfile.dumps({"format": 1, "workspace": self.workspace}),
        )
        write_settings(self.legacy_settings, "/elsewhere", "lab")
        write_project(self.workspace, "lab")
        migration = engine.startup_migration()
        self.assertEqual([item.name for item in migration.items], ["lab"])

    def test_unreadable_settings_use_the_defaults(self):
        write(locations.settings_file(), "workspace = \n")
        write_project(os.path.join(self.root, ".virtualbricks"), "lab")
        migration = engine.startup_migration()
        self.assertEqual([item.name for item in migration.items], ["lab"])
        with open(self.legacy_settings, "wb") as fp:
            fp.write(b"\xff\xfe")
        self.assertEqual(
            engine._legacy_app_settings(self.legacy_settings).workspace,
            os.path.join(self.root, ".virtualbricks"),
        )

    def test_in_place_migration(self):
        migration = engine.in_place_migration(dry_run=True)
        self.assertEqual(migration.items, [])
        self.assertTrue(migration.dry_run)
        write_settings(self.legacy_settings, self.workspace)
        migration = engine.in_place_migration()
        self.assertEqual(migration.workspace, self.workspace)
        self.assertEqual(migration.items[0].source, self.legacy_settings)
        other = write_settings(
            os.path.join(self.root, "other.conf"), "/srv/vb"
        )
        migration = engine.in_place_migration(other)
        self.assertEqual(migration.workspace, "/srv/vb")

    def test_migration_for(self):
        write(
            locations.settings_file(),
            tomlfile.dumps({"format": 1, "cowfmt": "cow"}),
        )
        migration = engine.migration_for(self.workspace)
        self.assertIsInstance(migration.target, engine.InPlace)
        self.assertEqual(migration.app_settings.cowfmt, "cow")
        migration = engine.migration_for(self.workspace, output=self.output)
        self.assertIsInstance(migration.target, engine.Folder)
        self.assertEqual(migration.app_settings.cowfmt, "qcow2")
        old = write_settings(os.path.join(self.root, "vb.conf"), "/srv/vb")
        migration = engine.migration_for(self.workspace, old, self.output)
        self.assertEqual(migration.app_settings.cowfmt, "qcow")
        self.assertEqual(migration.items[0].kind, "settings")


class TestImportedProject(EngineTestCase):

    def test_migrate(self):
        directory = os.path.join(self.root, "imported")
        write_project(self.root, "imported", CONFIG1)
        report = engine.migrate_imported_project(directory)
        self.assertEqual(report.errors, 0)
        data = tomlfile.load(os.path.join(directory, locations.PROJECT_FILE))
        self.assertIn("sender", data["bricks"])

    def test_uses_the_settings_of_new_projects(self):
        settings.set_app("cowfmt", "cow")
        directory = os.path.join(self.root, "imported")
        write_project(self.root, "imported", CONFIG1)
        engine.migrate_imported_project(directory)
        data = tomlfile.load(os.path.join(directory, locations.PROJECT_FILE))
        self.assertEqual(data["settings"]["cowfmt"], "cow")

    def test_no_project_file(self):
        directory = os.path.join(self.root, "imported")
        os.makedirs(directory)
        report = engine.migrate_imported_project(directory)
        self.assertEqual(
            [str(m) for m in report], [f"{directory}: no project file found"]
        )

    def test_invalid(self):
        directory = os.path.join(self.root, "imported")
        write_project(self.root, "imported", "[Switch:a]\n[Switch:a]\n")
        report = engine.migrate_imported_project(directory)
        self.assertEqual(report.errors, 1)
        self.assertIsInstance(report, Report)
        self.assertFalse(
            os.path.exists(os.path.join(directory, locations.PROJECT_FILE))
        )


class TestLock(unittest.TestCase):

    def setUp(self):
        isolate(self)

    def lock_in_place(self):
        lock = engine.lock_in_place()
        self.addCleanup(release, lock)
        return lock

    def test_lock(self):
        lock = self.lock_in_place()
        self.assertEqual(lock.name, locations.LOCK_FILE)
        self.assertTrue(lock.locked)
        # the application can't start, and a second migration can't run
        self.assertFalse(lock_is_free())
        self.assertIsNone(self.lock_in_place())
        lock.unlock()
        self.assertTrue(self.lock_in_place().locked)

    def test_lock_while_virtualbricks_runs(self):
        hold_lock(self)
        self.assertIsNone(self.lock_in_place())

    def test_lock_of_another_user(self):
        def lock(self):
            raise PermissionError("Operation not permitted")

        self.patch(lockfile.FilesystemLock, "lock", lock)
        self.assertIsNone(engine.lock_in_place())
