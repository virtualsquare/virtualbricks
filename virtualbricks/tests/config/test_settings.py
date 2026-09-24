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

import os

from twisted.trial import unittest

from virtualbricks import tools, locations
from virtualbricks.config import Report, settings, tomlfile
from virtualbricks.errors import NoOptionError
from virtualbricks.tests import FakeLogger, isolate, reset_settings


class SettingsTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.logger = FakeLogger()
        self.patch(settings, "logger", self.logger)
        self.ksm = []
        self.patch(tools, "check_ksm", lambda: True)
        self.patch(tools, "set_ksm", lambda enable: self.ksm.append(enable))


class TestCheckFormat(unittest.TestCase):

    def test_current(self):
        report = Report()
        self.assertTrue(settings.check_format({"format": 1}, report, "f"))
        self.assertEqual(len(report), 0)

    def test_newer(self):
        report = Report()
        self.assertFalse(settings.check_format({"format": 2}, report, "f"))
        self.assertEqual(
            [str(m) for m in report],
            ["f: written by a newer Virtualbricks (format 2)"],
        )
        self.assertTrue(report.has_errors)

    def test_unknown(self):
        for value in (None, "1", True, 0):
            report = Report()
            data = {} if value is None else {"format": value}
            self.assertTrue(settings.check_format(data, report, "f"))
            self.assertEqual(report.warnings, 1)


class TestValues(SettingsTestCase):

    def test_defaults(self):
        self.assertEqual(settings.get("term"), "/usr/bin/xterm")
        self.assertEqual(
            settings.get("workspace"),
            os.path.join(self.root, ".virtualbricks"),
        )
        self.assertTrue(settings.has_option("cowfmt"))
        self.assertFalse(settings.has_option("python"))

    def test_unknown(self):
        self.assertRaises(NoOptionError, settings.get, "python")
        self.assertRaises(NoOptionError, settings.set, "python", True)
        self.assertRaises(NoOptionError, settings.get_app, "python")
        self.assertRaises(NoOptionError, settings.set_app, "python", True)
        self.assertRaises(NoOptionError, settings.parse, "python", "1")

    def test_set_validates(self):
        self.assertRaises(ValueError, settings.set, "cowfmt", "qed")
        settings.set("cowfmt", "qcow")
        self.assertEqual(settings.get("cowfmt"), "qcow")

    def test_sudo_as_root(self):
        self.patch(os, "getuid", lambda: 0)
        self.assertEqual(settings.get("sudo"), "")
        self.assertEqual(settings.get_app("sudo"), "/usr/bin/gksu")

    def test_parse(self):
        self.assertIs(settings.parse("femaleplugs", "yes"), True)
        self.assertRaises(ValueError, settings.parse, "cowfmt", "qed")


class TestProjectSettings(SettingsTestCase):

    def test_new_project_starts_from_the_app_settings(self):
        settings.set("vdepath", "/opt/vde")
        project = settings.new_project_settings()
        self.assertEqual(project.vdepath, "/opt/vde")
        self.assertIsInstance(project, settings.ProjectSettings)

    def test_open_project_wins(self):
        project = settings.ProjectSettings(qemupath="/opt/qemu")
        settings.use_project(project)
        self.assertIs(settings.project_settings(), project)
        self.assertEqual(settings.get("qemupath"), "/opt/qemu")
        self.assertEqual(settings.get_app("qemupath"), "/usr/bin")
        settings.set("qemupath", "/srv/qemu")
        self.assertEqual(project.qemupath, "/srv/qemu")
        self.assertEqual(settings.get_app("qemupath"), "/usr/bin")
        # app-only settings are not per project
        settings.set("term", "/usr/bin/foot")
        self.assertEqual(settings.get_app("term"), "/usr/bin/foot")
        settings.set_app("qemupath", "/usr/local/bin")
        self.assertEqual(project.qemupath, "/srv/qemu")
        settings.use_project(None)
        self.assertEqual(settings.get("qemupath"), "/usr/local/bin")

    def test_project_keys(self):
        self.assertEqual(
            settings.PROJECT_KEYS,
            {"cowfmt", "erroronloop", "femaleplugs", "qemupath", "vdepath"},
        )


class TestLoadStore(SettingsTestCase):

    def path(self):
        return locations.settings_file()

    def test_first_start_saves_the_defaults(self):
        report = settings.load()
        self.assertEqual(len(report), 0)
        data = tomlfile.load(self.path())
        self.assertEqual(data["format"], 1)
        self.assertIs(data["ksm"], True)
        self.assertEqual(
            len(data), 1 + len(settings.schema.names(settings.AppSettings))
        )
        self.assertEqual(
            self.logger.formatted(),
            [f"Default settings saved to {self.path()}"],
        )

    def test_first_start_that_cant_save(self):
        self.patch(settings, "store", lambda path=None: False)
        settings.load()
        self.assertEqual(self.logger.events, [])

    def test_load(self):
        os.makedirs(os.path.dirname(self.path()))
        tomlfile.dump(
            {"format": 1, "term": "/usr/bin/foot", "color": 1}, self.path()
        )
        report = settings.load()
        self.assertEqual(settings.get("term"), "/usr/bin/foot")
        messages = [str(m) for m in report]
        self.assertIn("color: unknown field, dropped", messages)
        self.assertIn('cowfmt: missing, using the default "qcow2"', messages)
        self.assertEqual(self.ksm, [])

    def test_load_enables_ksm(self):
        os.makedirs(os.path.dirname(self.path()))
        data = {
            "format": 1,
            **settings.schema.dump(settings.AppSettings(ksm=True)),
        }
        tomlfile.dump(data, self.path())
        settings.load()
        self.assertEqual(self.ksm, [True])

    def test_explicit_path(self):
        path = self.mktemp()
        settings.load(path)
        self.assertTrue(os.path.isfile(path))
        settings.set("term", "x")
        self.assertTrue(settings.store())
        self.assertEqual(tomlfile.load(path)["term"], "x")

    def test_unreadable(self):
        os.makedirs(self.path())  # a directory can't be read as a file
        settings.load()
        self.assertEqual(self.logger.levels()[0], "error")
        self.assertFalse(settings.store())
        self.assertEqual(self.logger.levels()[-1], "warn")
        other = self.mktemp()
        self.assertTrue(settings.store(other))

    def test_invalid_toml(self):
        os.makedirs(os.path.dirname(self.path()))
        with open(self.path(), "w") as fp:
            fp.write("term = \n")
        settings.load()
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertFalse(settings.store())

    def test_newer_format_is_not_overwritten(self):
        os.makedirs(os.path.dirname(self.path()))
        tomlfile.dump({"format": 2, "term": "/x"}, self.path())
        report = settings.load()
        self.assertTrue(report.has_errors)
        self.assertEqual(settings.get("term"), "/usr/bin/xterm")
        self.assertFalse(settings.store())
        self.assertEqual(tomlfile.load(self.path())["format"], 2)

    def test_store_error(self):
        def fail(data, path):
            raise OSError("disk full")

        self.patch(tomlfile, "dump", fail)
        self.assertFalse(settings.store(self.mktemp()))
        self.assertEqual(self.logger.levels(), ["failure"])


class TestState(SettingsTestCase):

    def test_default(self):
        self.assertEqual(len(settings.load_state()), 0)
        self.assertEqual(settings.current_project(), "new_project")

    def test_set_current_project_stores_it(self):
        settings.load_state()
        settings.set_current_project("lab")
        self.assertEqual(
            tomlfile.load(locations.state_file()),
            {"format": 1, "current_project": "lab"},
        )
        settings.load_state()
        self.assertEqual(settings.current_project(), "lab")

    def test_explicit_path(self):
        path = self.mktemp()
        settings.set_current_project("x")  # to the default path
        settings.store_state(path)
        self.assertEqual(tomlfile.load(path)["current_project"], "x")
        settings.load_state(path)
        self.assertEqual(settings.current_project(), "x")

    def test_unreadable(self):
        os.makedirs(locations.state_file())
        settings.load_state()
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertEqual(settings.current_project(), "new_project")

    def test_warnings_are_logged(self):
        os.makedirs(os.path.dirname(locations.state_file()))
        tomlfile.dump({"current_project": "lab"}, locations.state_file())
        report = settings.load_state()
        self.assertEqual(report.warnings, 1)
        self.assertEqual(settings.current_project(), "lab")
        self.assertEqual(self.logger.levels(), ["warn"])

    def test_store_error(self):
        def fail(data, path):
            raise OSError("disk full")

        self.patch(tomlfile, "dump", fail)
        settings.store_state(self.mktemp())
        self.assertEqual(self.logger.levels(), ["failure"])
