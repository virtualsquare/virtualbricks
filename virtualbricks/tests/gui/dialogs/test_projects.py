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

"""The Projects window and the Remove dialog."""

import datetime
import os
import time

from twisted.internet import defer

from virtualbricks import engine, errors, locations
from virtualbricks.config.tomlfile import dump_toml, load_toml
from virtualbricks.config.workspace import DiskUsage
from virtualbricks.console import ampwire
from virtualbricks.tests.config.test_images import FakeWorkspace
from virtualbricks.tests import FakeLogger, FakeTrash
from virtualbricks.tests.gui import GuiTestCase, ProjectsGui, has_display

if has_display:
    from gi.repository import Gdk, GdkPixbuf, Gtk

    from virtualbricks.gui.dialogs import projectname, projects

NOW = datetime.datetime(2026, 9, 25, 15, 0)
MB = 1000 * 1000


class ProjectsTestCase(GuiTestCase):

    def setUp(self):
        super().setUp()
        self.gui = ProjectsGui(self.factory, self.manager)
        self.logger = FakeLogger()
        self.patch(projects, "logger", self.logger)
        self.patch(projectname, "logger", FakeLogger())
        self.patch(locations, "ensure_private_dir", lambda path: path)
        self.patch(self.manager, "make_runtime_dir", lambda: None)
        self.usage = {}
        self.trash = FakeTrash()
        self.patch(self.manager, "trasher", self.trash)
        self.dialogs = []
        test = self

        class NameDialog(projectname.ProjectNameDialog):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                test.dialogs.append(self)
                test.addCleanup(self.dialog.destroy)

        self.patch(projectname, "ProjectNameDialog", NameDialog)

    def disk_usage(self, name):
        if name in self.usage:
            usage = self.usage[name]
            if isinstance(usage, Exception):
                return defer.fail(usage)
            return defer.succeed(usage)
        return defer.Deferred()

    def lab(self, name, days=0, description="", bricks=None, images=None):
        self.manager.create(name, description)
        path = self.manager._project_file(name)
        data = load_toml(path)
        if bricks:
            data["bricks"] = bricks
        if images:
            data["images"] = {n: {"path": p} for n, p in images.items()}
        dump_toml(data, path)
        when = time.time() - days * 86400
        os.utime(path, (when, when))

    def window(self):
        window = projects.ProjectsWindow(self.gui, disk_usage=self.disk_usage)
        self.addCleanup(self.destroy, window)
        return window

    def destroy(self, window):
        if not window.destroyed:
            window.window.destroy()

    def names(self, window):
        return [row.summary.name for row in window.rows]


class TestOverAConnection(ProjectsTestCase):
    """The projects of another Virtualbricks: no archives, no file manager."""

    def test_what_waits(self):
        self.lab("ospf")
        self.gui.engine.local = False
        window = self.window()
        for button in (window.import_button, window.empty_import_button):
            self.assertFalse(button.get_sensitive())
            self.assertEqual(
                button.get_tooltip_text(), "Not over a connection, for now"
            )
        window.select("ospf")
        self.assertTrue(window.duplicate_button.get_sensitive())
        self.assertFalse(window.export_button.get_sensitive())
        self.assertFalse(window.actions.lookup_action("show").get_enabled())

    def test_the_list_cant_come(self):
        self.gui.engine.project_summaries = lambda: defer.fail(
            ampwire.CommandFailed("The connection to lab is lost")
        )
        window = self.window()
        self.assertTrue(window.info_bar.get_visible())
        self.assertEqual(
            window.info_label.get_text(),
            "Cannot list the projects: The connection to lab is lost",
        )

    def test_its_workspace(self):
        # the engine's, which is the one there over a connection
        other = FakeWorkspace(None)
        other.path = "/srv/labs"
        self.gui.engine.workspace = other
        window = self.window()
        self.assertIs(window.workspace, other)


class TestList(ProjectsTestCase):

    def test_no_projects(self):
        window = self.window()
        self.assertEqual(window.stack.get_visible_child_name(), "empty")
        window.empty_new_button.clicked()
        self.assertEqual(self.dialogs[0].kind, "new")
        window.empty_import_button.clicked()
        self.assertEqual(self.gui.calls, [("import",)])

    def test_the_most_recent_first(self):
        self.lab("old", days=30)
        self.lab("new", days=1)
        self.lab("today")
        window = self.window()
        self.assertEqual(window.stack.get_visible_child_name(), "projects")
        self.assertEqual(self.names(window), ["today", "new", "old"])
        # nothing open, nothing selected
        self.assertIsNone(window.selected)
        self.assertEqual(window.details_stack.get_visible_child_name(), "none")

    def test_rows(self):
        image = os.path.join(self.folder("images"), "deb.qcow2")
        with open(image, "w"):
            pass
        self.lab(
            "lab",
            days=1,
            description="\n# OSPF lab\n\nDetails",
            bricks={"vm": {"type": "qemu"}, "sw": {"type": "switch"}},
            images={"deb": image, "gone": "/nowhere"},
        )
        self.lab("open")
        self.manager.open("open", self.factory)
        window = self.window()
        rows = {row.summary.name: row for row in window.rows}
        lab = rows["lab"]
        self.assertEqual(lab.description_label.get_text(), "OSPF lab")
        self.assertEqual(
            lab.facts_label.get_text(),
            "2 bricks · Yesterday · 1 image missing",
        )
        self.assertTrue(
            lab.facts_label.get_style_context().has_class("warning")
        )
        self.assertFalse(lab.open_badge.get_visible())
        self.assertTrue(rows["open"].open_badge.get_visible())
        self.assertFalse(rows["open"].description_label.get_visible())
        # the open project is selected
        self.assertEqual(window.selected.name, "open")

    def test_unreadable(self):
        os.makedirs(os.path.join(self.manager.path, "bad"))
        with open(self.manager._project_file("bad"), "w") as fp:
            fp.write("[bricks\n")
        window = self.window()
        [row] = window.rows
        self.assertEqual(row.facts_label.get_text(), "Can't be read")
        window.select("bad")
        self.assertTrue(window.problem_label.get_visible())
        self.assertFalse(window.facts_grid.get_visible())
        self.assertFalse(window.open_button.get_sensitive())
        self.assertFalse(window.duplicate_button.get_sensitive())
        self.assertFalse(window.export_button.get_sensitive())
        self.assertFalse(window.actions.lookup_action("rename").get_enabled())
        window.open("bad")
        window.on_rename()
        self.assertEqual((self.gui.calls, self.dialogs), ([], []))

    def test_search(self):
        self.lab("ospf", description="three routers")
        self.lab("bgp", description="two AS")
        window = self.window()
        visible = lambda: [  # noqa: E731
            row.summary.name for row in window.rows if window._filter(row.row)
        ]
        window.search_entry.set_text("ROUTERS")
        self.assertEqual(visible(), ["ospf"])
        window.search_entry.set_text("bg")
        self.assertEqual(visible(), ["bgp"])
        window.on_search_changed(window.search_entry)

    def test_typing_searches(self):
        self.lab("ospf")
        window = self.window()
        window.window.show()
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        event.keyval = Gdk.KEY_o
        event.window = window.window.get_window()
        window.on_key_press(window.window, event)


class TestDetails(ProjectsTestCase):

    def test_details(self):
        self.lab(
            "lab",
            description="**OSPF** lab",
            bricks={"vm": {"type": "qemu"}},
            images={"gone": "/nowhere"},
        )
        self.usage["lab"] = DiskUsage(1500 * MB, 2000)
        window = self.window()
        window.select("lab")
        self.assertEqual(window.title_label.get_text(), "lab")
        self.assertEqual(
            window.path_label.get_text(), self.manager.project_path("lab")
        )
        readme = window.readme_view.get_buffer()
        self.assertEqual(
            readme.get_text(*readme.get_bounds(), False), "OSPF lab"
        )
        values = {k: v.get_text() for k, v in window.fact_values.items()}
        self.assertEqual(values["bricks"], "1 qemu")
        self.assertEqual(values["events"], "0")
        self.assertEqual(
            values["images"], "gone: /nowhere, not on this computer"
        )
        self.assertEqual(values["disks"], "1.5 GB")
        self.assertEqual(values["other"], "2.0 KB")
        self.assertTrue(values["used"].startswith("Today at"))
        self.assertTrue(window.open_button.get_sensitive())

    def test_an_empty_project(self):
        image = os.path.join(self.folder("images"), "deb")
        with open(image, "w"):
            pass
        self.lab("lab", images={"deb": image})
        window = self.window()
        window.select("lab")
        values = {k: v.get_text() for k, v in window.fact_values.items()}
        self.assertEqual(values["bricks"], "None")
        self.assertEqual(values["images"], f"deb: {image}")
        # the size is on its way
        self.assertEqual(values["disks"], "…")
        self.assertFalse(window.readme_view.get_visible())

    def test_the_pictures_of_the_readme(self):
        self.lab("lab", description="![the map](map.png) ![](../ospf.png)")
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 4, 3)
        pixbuf.savev(
            os.path.join(self.manager.project_path("lab"), "map.png"),
            "png",
            [],
            [],
        )
        window = self.window()
        window.select("lab")
        readme = window.readme_view.get_buffer()
        # the one of its folder
        self.assertEqual(
            readme.get_slice(*readme.get_bounds(), True), "\ufffc ../ospf.png"
        )
        [image] = window.readme_view.get_children()
        self.assertEqual(image.get_accessible().get_name(), "the map")

    def test_the_readme_is_drawn_on_the_pane(self):
        window = self.window()
        background = window.readme_view.get_style_context().get_property(
            "background-color", Gtk.StateFlags.NORMAL
        )
        self.assertEqual(background.alpha, 0)

    def test_the_open_project(self):
        self.lab("lab")
        self.manager.open("lab", self.factory)
        window = self.window()
        self.assertFalse(window.open_button.get_sensitive())
        self.assertEqual(
            window.open_button.get_tooltip_text(), "This project is open"
        )

    def test_sizes_that_cannot_be_read(self):
        self.lab("lab")
        self.usage["lab"] = OSError("gone")
        window = self.window()
        window.select("lab")
        self.assertEqual(window.fact_values["disks"].get_text(), "Unknown")

    def test_late_sizes(self):
        self.lab("a")
        self.lab("b")
        late = defer.Deferred()
        window = self.window()
        window._disk_usage = lambda name: (
            late if name == "a" else defer.Deferred()
        )
        window.select("a")
        window.select("b")
        late.callback(DiskUsage(5, 5))
        self.assertEqual(window.fact_values["disks"].get_text(), "…")
        failed = defer.Deferred()
        window._disk_usage = lambda name: failed
        window.select("a")
        window.window.destroy()
        failed.errback(OSError("late"))

    def test_the_thread(self):
        self.lab("lab")
        window = projects.ProjectsWindow(self.gui)
        self.addCleanup(self.destroy, window)
        called = []
        self.patch(
            engine.threads,
            "deferToThread",
            lambda f, *args: called.append((f, args)) or defer.Deferred(),
        )
        window.select("lab")
        self.assertEqual(called, [(self.manager.disk_usage, ("lab",))])


class TestActions(ProjectsTestCase):

    def setUp(self):
        super().setUp()
        self.lab("lab")
        self.lab("other", days=1)

    def test_open(self):
        window = self.window()
        window.select("lab")
        window.open_button.clicked()
        self.assertEqual(self.gui.calls, [("open", "lab"), ("title",)])
        self.assertEqual(self.manager.current.name, "lab")
        self.assertTrue(window.destroyed)

    def test_a_click_only_selects(self):
        window = self.window()
        self.assertFalse(window.list.get_activate_on_single_click())
        window.list.select_row(window.rows[1].row)
        self.assertEqual(window.selected.name, "other")
        self.assertIsNone(self.manager.current)
        self.assertFalse(window.destroyed)

    def test_open_by_activating_a_row(self):
        window = self.window()
        window.on_row_activated(window.list, window.rows[1].row)
        self.assertEqual(self.manager.current.name, "other")

    def test_open_fails(self):
        def on_open(name):
            raise errors.BrickRunningError("running bricks")

        self.gui.on_open = on_open
        window = self.window()
        window.select("lab")
        window.open_button.clicked()
        self.assertFalse(window.destroyed)
        self.assertTrue(window.info_bar.get_visible())
        self.assertIn("running bricks", window.info_label.get_text())
        self.assertEqual(self.logger.levels(), ["error"])
        window.info_bar.response(Gtk.ResponseType.CLOSE)
        self.assertFalse(window.info_bar.get_visible())

    def test_open_nothing(self):
        window = self.window()
        window.on_open_clicked(None)
        window.on_duplicate_clicked(None)
        window.on_export_clicked(None)
        window.on_rename()
        window.on_show()
        self.assertIsNone(window.on_remove())
        window.open("gone")
        self.assertEqual((self.gui.calls, self.dialogs), ([], []))

    def test_new(self):
        window = self.window()
        window.new_button.clicked()
        [dialog] = self.dialogs
        self.assertEqual(dialog.kind, "new")
        self.assertIs(dialog.dialog.get_transient_for(), window.window)
        dialog.name_entry.set_text("ospf")
        dialog.dialog.response(Gtk.ResponseType.OK)
        # the new project is open: nothing more to do here
        self.assertTrue(window.destroyed)

    def test_duplicate_and_rename(self):
        window = self.window()
        window.select("lab")
        window.duplicate_button.clicked()
        dialog = self.dialogs[-1]
        self.assertEqual((dialog.kind, dialog.original), ("duplicate", "lab"))
        dialog.open_check.set_active(False)
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertIn("lab-copy", self.names(window))
        self.assertEqual(window.selected.name, "lab-copy")
        window.actions.activate_action("rename", None)
        dialog = self.dialogs[-1]
        self.assertEqual(
            (dialog.kind, dialog.original), ("rename", "lab-copy")
        )
        dialog.name_entry.set_text("copy")
        dialog.dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(window.selected.name, "copy")
        self.assertIn("copy", self.names(window))

    def test_a_name_dialog_after_the_window(self):
        window = self.window()
        window.window.destroy()
        window.on_name_done("lab")

    def test_import(self):
        window = self.window()
        window.import_button.clicked()
        self.assertEqual(self.gui.calls, [("import",)])
        self.lab("imported")
        self.gui.import_closed()
        self.assertIn("imported", self.names(window))
        window.window.destroy()
        self.gui.import_closed()

    def test_export(self):
        window = self.window()
        window.select("other")
        window.export_button.clicked()
        self.assertEqual(self.gui.calls, [("export", "other")])

    def test_show_in_files(self):
        shown = []
        self.patch(
            Gtk, "show_uri_on_window", lambda w, uri, t: shown.append(uri)
        )
        window = self.window()
        window.select("lab")
        window.actions.activate_action("show", None)
        self.assertEqual(len(shown), 1)
        self.assertTrue(shown[0].startswith("file://"))
        self.assertTrue(shown[0].endswith("/lab"))

        def fail(w, uri, t):
            raise RuntimeError("no file manager")

        self.patch(Gtk, "show_uri_on_window", fail)
        window.on_show()
        self.assertEqual(self.logger.levels(), ["error"])

    def test_keys(self):
        window = self.window()
        window.select("lab")
        event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
        event.keyval = Gdk.KEY_F2
        self.assertTrue(window.on_key_press(window.window, event))
        self.assertEqual(self.dialogs[-1].kind, "rename")
        event.keyval = Gdk.KEY_Delete
        self.patch(projects.RemoveDialog, "show", lambda self, parent: None)
        self.assertTrue(window.on_key_press(window.window, event))
        # the search entry keeps its keys
        window.window.show()
        window.search_entry.grab_focus()
        self.assertFalse(window.on_key_press(window.window, event))

    def test_closed(self):
        window = self.window()
        window.window.destroy()
        self.assertTrue(window.destroyed)

    def test_show_problem(self):
        window = self.window()
        window.show_problem("lab can't be opened")
        self.assertTrue(window.info_bar.get_visible())
        parent = Gtk.Window()
        self.addCleanup(parent.destroy)
        window.show(parent)
        self.assertIs(window.window.get_transient_for(), parent)


class TestRemove(ProjectsTestCase):

    def setUp(self):
        super().setUp()
        self.lab("lab")
        self.lab("open")
        self.manager.open("open", self.factory)

    def dialog(self, name, usage=None):
        dialog = projects.RemoveDialog(
            self.gui.engine, self.manager, self.manager.summary(name), usage
        )
        self.addCleanup(dialog.dialog.destroy)
        return dialog

    def secondary(self, dialog):
        return dialog.dialog.get_property("secondary-text")

    def test_trash(self):
        dialog = self.dialog("lab", DiskUsage(1500 * MB, 10))
        self.assertEqual(dialog.dialog.get_property("text"), "Remove lab?")
        self.assertIn("with 1.5 GB of private disks", self.secondary(dialog))
        self.assertIn("to the trash", self.secondary(dialog))
        self.assertIsNotNone(dialog.trash_button)
        removed = []
        dialog.on_done = removed.append
        dialog.dialog.response(dialog.TRASH)
        self.assertEqual(
            self.trash.trashed, [self.manager.project_path("lab")]
        )
        self.assertEqual(removed, ["lab"])

    def test_delete(self):
        dialog = self.dialog("lab", DiskUsage(0, 2000))
        self.assertIn("Its folder, 2.0 KB, goes", self.secondary(dialog))
        dialog.dialog.response(dialog.DELETE)
        self.assertEqual(self.manager.names(), ["open"])

    def test_no_trash(self):
        self.trash.allowed = False
        dialog = self.dialog("lab", DiskUsage(0, 0))
        self.assertIsNone(dialog.trash_button)
        self.assertIn("no trash", self.secondary(dialog))

    def test_the_size_is_read(self):
        # by the engine, which counts in a thread or there
        counting = defer.Deferred()
        self.gui.engine.disk_usage = lambda name: counting
        dialog = projects.RemoveDialog(
            self.gui.engine, self.manager, self.manager.summary("lab")
        )
        self.addCleanup(dialog.dialog.destroy)
        self.assertIn("Its folder goes", self.secondary(dialog))
        counting.callback(DiskUsage(0, 2000))
        self.assertIn("Its folder, 2.0 KB, goes", self.secondary(dialog))

    def test_the_size_cant_be_read(self):
        self.gui.engine.disk_usage = lambda name: defer.fail(OSError("gone"))
        dialog = projects.RemoveDialog(
            self.gui.engine, self.manager, self.manager.summary("lab")
        )
        self.addCleanup(dialog.dialog.destroy)
        self.assertIn("Its folder goes", self.secondary(dialog))

    def test_the_open_project(self):
        dialog = self.dialog("open", DiskUsage(0, 0))
        self.assertEqual(dialog.dialog.get_property("text"), "open is open")
        self.assertIsNone(dialog.delete_button)
        self.assertIn("Open another project first", self.secondary(dialog))

    def test_cancel_and_failures(self):
        dialog = self.dialog("lab", DiskUsage(0, 0))
        dialog.dialog.response(Gtk.ResponseType.CANCEL)
        self.assertEqual(self.manager.names(), ["lab", "open"])
        dialog = self.dialog("lab", DiskUsage(0, 0))
        self.manager.delete("lab")
        removed = []
        dialog.on_done = removed.append
        dialog.dialog.response(dialog.DELETE)
        self.assertEqual(removed, [])
        self.assertEqual(self.logger.levels(), ["error"])

    def test_from_the_window(self):
        self.patch(projects.RemoveDialog, "show", lambda self, parent: None)
        window = self.window()
        window.select("lab")
        dialog = window.on_remove()
        dialog.dialog.response(dialog.DELETE)
        self.assertEqual(self.names(window), ["open"])
        window.window.destroy()
        window.on_removed("lab")


class TestHelpers(GuiTestCase):

    def test_when(self):
        def at(*args):
            return datetime.datetime(*args).timestamp()

        when = projects.when
        self.assertEqual(when(at(2026, 9, 25, 14, 3), NOW), "Today at 14:03")
        self.assertEqual(when(at(2026, 9, 24, 23, 0), NOW), "Yesterday")
        self.assertEqual(when(at(2026, 8, 3), NOW), "3 Aug")
        self.assertEqual(when(at(2024, 8, 3), NOW), "3 Aug 2024")
        self.assertTrue(when(time.time()).startswith("Today"))

    def test_sizes(self):
        self.assertEqual(projects.human_size(12), "12 B")
        self.assertEqual(projects.human_size(612 * MB), "612.0 MB")
