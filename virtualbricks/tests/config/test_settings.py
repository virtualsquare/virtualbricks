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

from virtualbricks import ksm, locations
from virtualbricks.config.settings import (
    PROJECT_KEYS,
    AppSettings,
    ProjectSettings,
    current_project,
    get_setting,
    has_option,
    load_settings,
    load_state,
    new_project_settings,
    parse_setting,
    project_settings,
    set_setting,
    setting_kind,
    store_settings,
)
from virtualbricks.config.report import Report
from virtualbricks.config.schema import dump_record, field_names
from virtualbricks.config.tomlfile import dump_toml, load_toml
from virtualbricks.config import settings
from virtualbricks.config.settings import (
    check_format,
    set_current_project,
    store_state,
    use_project,
)
from virtualbricks.tests import FakeLogger, isolate, reset_settings


class SettingsTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.logger = FakeLogger()
        self.patch(settings, "logger", self.logger)
        self.ksm = []
        self.patch(ksm, "check_ksm", lambda: True)
        self.patch(ksm, "set_ksm", lambda enable: self.ksm.append(enable))


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
        self.assertEqual(get_setting("terminal"), "/usr/bin/xterm")
        self.assertEqual(
            get_setting("workspace"),
            os.path.join(self.root, ".virtualbricks"),
        )
        # a setting of a project, while none is open
        self.assertEqual(get_setting("qemu_path"), "/usr/bin")

    def test_has_option(self):
        self.assertTrue(has_option("terminal"))
        self.assertTrue(has_option("cow_format"))
        self.assertFalse(has_option("python"))

    def test_set_validates(self):
        self.assertRaises(ValueError, set_setting, "tray_icon", "maybe")
        set_setting("tray_icon", False)
        self.assertIs(get_setting("tray_icon"), False)
        use_project(ProjectSettings())
        self.assertRaises(ValueError, set_setting, "cow_format", "qed")
        set_setting("cow_format", "qcow")
        self.assertEqual(get_setting("cow_format"), "qcow")

    def test_parse(self):
        self.assertIs(parse_setting("allow_female_plugs", "yes"), True)
        self.assertIs(parse_setting("tray_icon", "no"), False)
        self.assertRaises(ValueError, parse_setting, "cow_format", "qed")

    def test_setting_kind(self):
        self.assertEqual(setting_kind("cow_format").format("qcow"), '"qcow"')
        self.assertEqual(setting_kind("tray_icon").format(True), "true")
        self.assertRaises(KeyError, setting_kind, "python")

    def test_unknown_name_is_an_error(self):
        self.assertRaises(AttributeError, get_setting, "python")
        self.assertRaises(KeyError, parse_setting, "python", "1")

    def test_setting_an_unknown_name_adds_nothing(self):
        self.assertRaises(AttributeError, set_setting, "python", True)
        self.assertRaises(AttributeError, get_setting, "python")


class TestProjectSettings(SettingsTestCase):

    def test_no_project_is_open(self):
        self.assertIsNone(project_settings())
        self.assertEqual(get_setting("cow_format"), "qcow2")
        error = self.assertRaises(
            ValueError, set_setting, "cow_format", "qcow"
        )
        self.assertEqual(
            str(error),
            "cow_format is a setting of a project, and none is open",
        )
        self.assertEqual(get_setting("cow_format"), "qcow2")

    def test_the_open_project(self):
        project = ProjectSettings(qemu_path="/opt/qemu")
        use_project(project)
        self.assertIs(project_settings(), project)
        self.assertEqual(get_setting("qemu_path"), "/opt/qemu")
        set_setting("qemu_path", "/srv/qemu")
        self.assertEqual(project.qemu_path, "/srv/qemu")
        # the settings of the application aren't the project's
        set_setting("terminal", "/usr/bin/foot")
        self.assertEqual(get_setting("terminal"), "/usr/bin/foot")
        use_project(None)
        self.assertEqual(get_setting("qemu_path"), "/usr/bin")
        self.assertEqual(get_setting("terminal"), "/usr/bin/foot")

    def test_a_new_project_copies_the_open_one(self):
        project = ProjectSettings(vde_path="/opt/vde", cow_format="qcow")
        use_project(project)
        new = new_project_settings()
        self.assertEqual(new, project)
        new.cow_format = "cow"
        self.assertEqual(project.cow_format, "qcow")

    def test_a_new_project_without_an_open_one(self):
        self.assertEqual(new_project_settings(), ProjectSettings())

    def test_unknown_name_with_a_project_open(self):
        project = ProjectSettings()
        use_project(project)
        self.assertRaises(AttributeError, get_setting, "python")
        self.assertRaises(AttributeError, set_setting, "python", True)
        self.assertEqual(project, ProjectSettings())

    def test_project_keys(self):
        self.assertEqual(
            PROJECT_KEYS,
            {
                "cow_format",
                "log_link_loops",
                "allow_female_plugs",
                "qemu_path",
                "vde_path",
            },
        )
        # none of them is a setting of the application
        self.assertFalse(PROJECT_KEYS & set(field_names(AppSettings)))


class TestLoadStore(SettingsTestCase):

    def path(self):
        return locations.settings_file()

    def test_first_start_saves_the_defaults(self):
        report = load_settings()
        self.assertEqual(len(report), 0)
        data = load_toml(self.path())
        self.assertEqual(data["format"], 1)
        self.assertIs(data["kernel_samepage_merging"], True)
        self.assertEqual(len(data), 1 + len(field_names(AppSettings)))
        self.assertEqual(
            self.logger.formatted(),
            [f"Default settings saved to {self.path()}"],
        )

    def test_first_start_that_cant_save(self):
        self.patch(settings, "store_settings", lambda path=None: False)
        load_settings()
        self.assertEqual(self.logger.events, [])

    def test_load(self):
        os.makedirs(os.path.dirname(self.path()))
        # an older settings.toml also has the settings of new projects
        dump_toml(
            {
                "format": 1,
                "terminal": "/usr/bin/foot",
                "color": 1,
                "cow_format": "cow",
            },
            self.path(),
        )
        report = load_settings()
        self.assertEqual(get_setting("terminal"), "/usr/bin/foot")
        messages = [str(m) for m in report]
        self.assertIn("color: unknown field, dropped", messages)
        self.assertIn("cow_format: unknown field, dropped", messages)
        self.assertIn("tray_icon: missing, using the default true", messages)
        self.assertEqual(get_setting("cow_format"), "qcow2")
        self.assertEqual(self.ksm, [])

    def test_load_enables_ksm(self):
        os.makedirs(os.path.dirname(self.path()))
        data = {
            "format": 1,
            **dump_record(AppSettings(kernel_samepage_merging=True)),
        }
        dump_toml(data, self.path())
        load_settings()
        self.assertEqual(self.ksm, [True])

    def test_explicit_path(self):
        path = self.mktemp()
        load_settings(path)
        self.assertTrue(os.path.isfile(path))
        set_setting("terminal", "x")
        self.assertTrue(store_settings())
        self.assertEqual(load_toml(path)["terminal"], "x")

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
            fp.write("terminal = \n")
        load_settings()
        self.assertEqual(self.logger.levels(), ["error"])
        self.assertFalse(store_settings())

    def test_newer_format_is_not_overwritten(self):
        os.makedirs(os.path.dirname(self.path()))
        dump_toml({"format": 2, "terminal": "/x"}, self.path())
        report = load_settings()
        self.assertTrue(report.has_errors)
        self.assertEqual(get_setting("terminal"), "/usr/bin/xterm")
        self.assertFalse(store_settings())
        self.assertEqual(load_toml(self.path())["format"], 2)

    def test_store_error(self):
        def fail(*args):
            raise OSError("disk full")

        self.patch(settings, "dump_toml", fail)
        self.assertFalse(store_settings(self.mktemp()))
        self.assertEqual(self.logger.levels(), ["failure"])

    def test_comments(self):
        load_settings()
        set_setting("terminal", "/usr/bin/foot")
        self.assertTrue(store_settings())
        with open(self.path(), encoding="utf-8") as fp:
            text = fp.read()
        self.assertTrue(text.startswith("# " + settings.SETTINGS_HEADER[:20]))
        self.assertIn(
            "\n# The version of the layout of this file\nformat = 1\n", text
        )
        self.assertIn(
            "\n# The terminal that opens the consoles of the bricks"
            ' (default "/usr/bin/xterm")\n'
            'terminal = "/usr/bin/foot"\n',
            text,
        )
        self.assertIn("\ntray_icon = true  # default\n", text)
        # the file reads back as its data
        self.assertEqual(
            load_toml(self.path()), {"format": 1, **dump_record(settings._app)}
        )


class TestState(SettingsTestCase):

    def test_default(self):
        self.assertEqual(len(load_state()), 0)
        self.assertEqual(current_project(), "new_project")

    def test_set_current_project_stores_it(self):
        load_state()
        set_current_project("lab")
        with open(locations.state_file(), encoding="utf-8") as fp:
            text = fp.read()
        self.assertTrue(text.startswith("# " + settings.STATE_HEADER[:20]))
        self.assertIn(
            "# The project that opens at start"
            ' (default "new_project")\ncurrent_project = "lab"\n',
            text,
        )
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
        def fail(*args):
            raise OSError("disk full")

        self.patch(settings, "dump_toml", fail)
        store_state(self.mktemp())
        self.assertEqual(self.logger.levels(), ["failure"])
