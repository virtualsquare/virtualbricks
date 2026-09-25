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

from virtualbricks import locations, tools
from virtualbricks.config import (
    PROJECT_KEYS,
    AppSettings,
    ProjectSettings,
    Report,
    check_format,
    current_project,
    dump_record,
    dump_toml,
    field_names,
    get_app_setting,
    get_setting,
    has_option,
    load_settings,
    load_state,
    load_toml,
    new_project_settings,
    parse_setting,
    project_settings,
    set_app_setting,
    set_current_project,
    set_setting,
    settings,
    store_settings,
    store_state,
    tomlfile,
    use_project,
)
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
        self.assertTrue(check_format({"format": 1}, report, "f"))
        self.assertEqual(len(report), 0)

    def test_newer(self):
        report = Report()
        self.assertFalse(check_format({"format": 2}, report, "f"))
        self.assertEqual(
            [str(m) for m in report],
            ["f: written by a newer Virtualbricks (format 2)"],
        )
        self.assertTrue(report.has_errors)

    def test_unknown(self):
        for value in (None, "1", True, 0):
            report = Report()
            data = {} if value is None else {"format": value}
            self.assertTrue(check_format(data, report, "f"))
            self.assertEqual(report.warnings, 1)


class TestValues(SettingsTestCase):

    def test_defaults(self):
        self.assertEqual(get_setting("term"), "/usr/bin/xterm")
        self.assertEqual(
            get_setting("workspace"),
            os.path.join(self.root, ".virtualbricks"),
        )
        self.assertTrue(has_option("cowfmt"))
        self.assertFalse(has_option("python"))

    def test_unknown(self):
        self.assertRaises(NoOptionError, get_setting, "python")
        self.assertRaises(NoOptionError, set_setting, "python", True)
        self.assertRaises(NoOptionError, get_app_setting, "python")
        self.assertRaises(NoOptionError, set_app_setting, "python", True)
        self.assertRaises(NoOptionError, parse_setting, "python", "1")

    def test_set_validates(self):
        self.assertRaises(ValueError, set_setting, "cowfmt", "qed")
        set_setting("cowfmt", "qcow")
        self.assertEqual(get_setting("cowfmt"), "qcow")

    def test_sudo_as_root(self):
        self.patch(os, "getuid", lambda: 0)
        self.assertEqual(get_setting("sudo"), "")
        self.assertEqual(get_app_setting("sudo"), "/usr/bin/gksu")

    def test_parse(self):
        self.assertIs(parse_setting("femaleplugs", "yes"), True)
        self.assertRaises(ValueError, parse_setting, "cowfmt", "qed")


class TestProjectSettings(SettingsTestCase):

    def test_new_project_starts_from_the_app_settings(self):
        set_setting("vdepath", "/opt/vde")
        project = new_project_settings()
        self.assertEqual(project.vdepath, "/opt/vde")
        self.assertIsInstance(project, ProjectSettings)

    def test_open_project_wins(self):
        project = ProjectSettings(qemupath="/opt/qemu")
        use_project(project)
        self.assertIs(project_settings(), project)
        self.assertEqual(get_setting("qemupath"), "/opt/qemu")
        self.assertEqual(get_app_setting("qemupath"), "/usr/bin")
        set_setting("qemupath", "/srv/qemu")
        self.assertEqual(project.qemupath, "/srv/qemu")
        self.assertEqual(get_app_setting("qemupath"), "/usr/bin")
        # app-only settings are not per project
        set_setting("term", "/usr/bin/foot")
        self.assertEqual(get_app_setting("term"), "/usr/bin/foot")
        set_app_setting("qemupath", "/usr/local/bin")
        self.assertEqual(project.qemupath, "/srv/qemu")
        use_project(None)
        self.assertEqual(get_setting("qemupath"), "/usr/local/bin")

    def test_project_keys(self):
        self.assertEqual(
            PROJECT_KEYS,
            {"cowfmt", "erroronloop", "femaleplugs", "qemupath", "vdepath"},
        )


class TestLoadStore(SettingsTestCase):

    def path(self):
        return locations.settings_file()

    def test_first_start_saves_the_defaults(self):
        report = load_settings()
        self.assertEqual(len(report), 0)
        data = load_toml(self.path())
        self.assertEqual(data["format"], 1)
        self.assertIs(data["ksm"], True)
        self.assertEqual(len(data), 1 + len(field_names(AppSettings)))
        self.assertEqual(
            self.logger.formatted(),
            [f"Default settings saved to {self.path()}"],
        )

    def test_first_start_that_cant_save(self):
        self.patch(settings, "store", lambda path=None: False)
        load_settings()
        self.assertEqual(self.logger.events, [])

    def test_load(self):
        os.makedirs(os.path.dirname(self.path()))
        dump_toml(
            {"format": 1, "term": "/usr/bin/foot", "color": 1}, self.path()
        )
        report = load_settings()
        self.assertEqual(get_setting("term"), "/usr/bin/foot")
        messages = [str(m) for m in report]
        self.assertIn("color: unknown field, dropped", messages)
        self.assertIn('cowfmt: missing, using the default "qcow2"', messages)
        self.assertEqual(self.ksm, [])

    def test_load_enables_ksm(self):
        os.makedirs(os.path.dirname(self.path()))
        data = {
            "format": 1,
            **dump_record(AppSettings(ksm=True)),
        }
        dump_toml(data, self.path())
        load_settings()
        self.assertEqual(self.ksm, [True])

    def test_explicit_path(self):
        path = self.mktemp()
        load_settings(path)
        self.assertTrue(os.path.isfile(path))
        set_setting("term", "x")
        self.assertTrue(store_settings())
        self.assertEqual(load_toml(path)["term"], "x")

    def test_unreadable(self):
        os.makedirs(self.path())  # a directory can't be read as a file
        load_settings()
        self.assertEqual(self.logger.levels()[0], "error")
        self.assertFalse(store_settings())
        self.assertEqual(self.logger.levels()[-1], "warn")
        other = self.mktemp()
        self.assertTrue(store_settings(other))

    def test_invalid_toml(self):
        os.makedirs(os.path.dirname(self.path()))
        with open(self.path(), "w") as fp:
            fp.write("term = \n")
        load_settings()
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertFalse(store_settings())

    def test_newer_format_is_not_overwritten(self):
        os.makedirs(os.path.dirname(self.path()))
        dump_toml({"format": 2, "term": "/x"}, self.path())
        report = load_settings()
        self.assertTrue(report.has_errors)
        self.assertEqual(get_setting("term"), "/usr/bin/xterm")
        self.assertFalse(store_settings())
        self.assertEqual(load_toml(self.path())["format"], 2)

    def test_store_error(self):
        def fail(data, path):
            raise OSError("disk full")

        self.patch(tomlfile, "dump", fail)
        self.assertFalse(store_settings(self.mktemp()))
        self.assertEqual(self.logger.levels(), ["failure"])


class TestState(SettingsTestCase):

    def test_default(self):
        self.assertEqual(len(load_state()), 0)
        self.assertEqual(current_project(), "new_project")

    def test_set_current_project_stores_it(self):
        load_state()
        set_current_project("lab")
        self.assertEqual(
            load_toml(locations.state_file()),
            {"format": 1, "current_project": "lab"},
        )
        load_state()
        self.assertEqual(current_project(), "lab")

    def test_explicit_path(self):
        path = self.mktemp()
        set_current_project("x")  # to the default path
        store_state(path)
        self.assertEqual(load_toml(path)["current_project"], "x")
        load_state(path)
        self.assertEqual(current_project(), "x")

    def test_unreadable(self):
        os.makedirs(locations.state_file())
        load_state()
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertEqual(current_project(), "new_project")

    def test_warnings_are_logged(self):
        os.makedirs(os.path.dirname(locations.state_file()))
        dump_toml({"current_project": "lab"}, locations.state_file())
        report = load_state()
        self.assertEqual(report.warnings, 1)
        self.assertEqual(current_project(), "lab")
        self.assertEqual(self.logger.levels(), ["warn"])

    def test_store_error(self):
        def fail(data, path):
            raise OSError("disk full")

        self.patch(tomlfile, "dump", fail)
        store_state(self.mktemp())
        self.assertEqual(self.logger.levels(), ["failure"])
