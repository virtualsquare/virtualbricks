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

"""Importing a project: the plan, its defaults, and the import itself."""

import os
import stat
import tarfile

from twisted.trial import unittest

from virtualbricks import locations
from virtualbricks.config import (
    ArchiveContents,
    ArchiveError,
    ArchiveMember,
    ImportResult,
    Workspace,
    archive,
    dumps,
    importing,
    load_toml,
    plan_import,
    set_app_setting,
    update_plan,
)
from virtualbricks.config.archive import Tool
from virtualbricks.config.importing import ImageUse, MachinePath
from virtualbricks.tests import isolate, reset_settings
from virtualbricks.tests.config.test_archive import (
    LEGACY,
    TOOLS,
    add,
    make_archive,
    sparse_file,
)

MiB = 1 << 20
FAKE_QEMU_IMG = """#!/bin/sh
echo "$@" >> "{log}"
case "$1" in
    info) echo '{{"format": "raw"}}' ;;
    rebase) [ -e "{fail}" ] && {{ echo "cannot rebase" >&2; exit 1; }} ;;
esac
exit 0
"""


def project(images=None, bricks=None, settings=None):
    data = {"format": 1, "settings": settings or {}}
    if images:
        data["images"] = {
            name: {"path": path} for name, path in images.items()
        }
    if bricks:
        data["bricks"] = bricks
    return data


def vm(*disks):
    """A virtual machine with a private disk for each (device, image)."""

    return {
        "type": "qemu",
        "disks": {
            device: {"image": image, "private": True}
            for device, image in disks
        },
    }


class ImportingTestCase(unittest.TestCase):

    def setUp(self):
        self.root = isolate(self)
        reset_settings(self)
        self.workspace = Workspace(os.path.join(self.root, "workspace"))
        self.library = os.path.join(self.workspace.path, "vimages")
        os.makedirs(self.library)

    def path(self, *segments):
        return os.path.join(self.root, *segments)

    def file(self, path, data=b""):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fp:
            fp.write(data)
        return path

    def contents(
        self, data, images=None, complete=True, path=None, description=""
    ):
        members = [ArchiveMember("project.toml", 10, "project")]
        for name, size in (images or {}).items():
            members.append(ArchiveMember(f".images/{name}", size, "image"))
        return ArchiveContents(
            path or self.path("lab.vbp"), data, description, members, complete
        )


class TestNames(ImportingTestCase):

    def test_archive_name(self):
        name = importing.archive_name
        self.assertEqual(name("/a/ospf-lab.vbp"), "ospf-lab")
        self.assertEqual(name("/a/lab.tar.gz"), "lab")
        self.assertEqual(name("/a/LAB.TGZ"), "LAB")
        self.assertEqual(name("/a/lab.tar"), "lab")
        self.assertEqual(name("/a/lab"), "lab")

    def test_free_file(self):
        path = os.path.join(self.library, "deb.qcow2")
        self.assertEqual(importing.free_file(path), path)
        self.file(path)
        self.file(os.path.join(self.library, "deb.1.qcow2"))
        self.assertEqual(
            importing.free_file(path),
            os.path.join(self.library, "deb.2.qcow2"),
        )

    def test_the_name_of_the_project(self):
        data = project()
        plan = plan_import(self.contents(data), self.workspace)
        self.assertEqual(plan.name, "lab")
        self.workspace.create("lab")
        plan = plan_import(self.contents(data), self.workspace)
        self.assertEqual(plan.name, "lab-2")
        long_name = self.path("x" * 50 + ".vbp")
        plan = plan_import(self.contents(data, path=long_name), self.workspace)
        self.assertEqual(plan.name, "x" * 38)
        hidden = self.path("..vbp")
        plan = plan_import(self.contents(data, path=hidden), self.workspace)
        self.assertEqual(plan.name, "imported")


class TestPlan(ImportingTestCase):

    def plan(self, images, in_archive=None, complete=True, bricks=None):
        data = project(images, bricks)
        return plan_import(
            self.contents(data, in_archive, complete), self.workspace
        )

    def test_an_image_in_the_archive_is_copied(self):
        plan = self.plan(
            {"deb": "/other/deb.qcow2"},
            {"deb": 100},
            bricks={"vm": vm(("hda", "deb"), ("hdb", "deb"))},
        )
        [image] = plan.images
        self.assertEqual(image.choice, "copy")
        self.assertEqual(image.path, os.path.join(self.library, "deb.qcow2"))
        self.assertEqual(image.used_by, ["vm.hda", "vm.hdb"])
        self.assertEqual(image.in_archive, 100)
        self.assertTrue(image.known)
        self.assertEqual(plan.bytes_to_copy(), 100)

    def test_ours_if_the_library_has_it(self):
        self.file(os.path.join(self.library, "deb.qcow2"), b"x" * 100)
        [image] = self.plan({"deb": "/other/deb.qcow2"}, {"deb": 100}).images
        self.assertEqual(image.choice, "use")
        self.assertEqual(image.path, os.path.join(self.library, "deb.qcow2"))

    def test_another_image_with_the_same_name(self):
        self.file(os.path.join(self.library, "deb.qcow2"), b"x" * 99)
        [image] = self.plan({"deb": "/other/deb.qcow2"}, {"deb": 100}).images
        self.assertEqual(image.choice, "copy")
        self.assertEqual(image.path, os.path.join(self.library, "deb.1.qcow2"))

    def test_an_image_not_in_the_archive(self):
        here = self.file(self.path("images", "here.qcow2"))
        self.file(os.path.join(self.library, "lib.qcow2"))
        self.file(os.path.join(self.library, "named"))
        plan = self.plan(
            {
                "here": here,
                "lib": "/other/lib.qcow2",
                "named": "",
                "gone": "/other/gone.qcow2",
            }
        )
        choices = {i.name: (i.choice, i.path) for i in plan.images}
        self.assertEqual(
            choices,
            {
                "here": ("use", here),
                "lib": ("use", os.path.join(self.library, "lib.qcow2")),
                "named": ("use", os.path.join(self.library, "named")),
                "gone": ("skip", ""),
            },
        )
        self.assertEqual(plan.bytes_to_copy(), 0)

    def test_before_the_end_of_the_archive(self):
        here = self.file(self.path("here.qcow2"))
        plan = self.plan({"deb": here, "gone": "/gone"}, {}, complete=False)
        deb, gone = plan.images
        self.assertFalse(deb.known)
        self.assertEqual(deb.choice, "copy")
        self.assertEqual(deb.fallback, here)
        self.assertEqual(gone.fallback, "")
        # the archive had deb, not gone
        update_plan(plan, self.contents(plan.contents.data, {"deb": 7}))
        self.assertEqual(
            (deb.known, deb.choice, deb.in_archive), (True, "copy", 7)
        )
        self.assertEqual((gone.known, gone.choice), (True, "skip"))

    def test_update_a_plan_that_knew(self):
        plan = self.plan({"deb": "/gone"}, {"deb": 5})
        update_plan(plan, self.contents(plan.contents.data, {"deb": 9}))
        self.assertEqual(plan.images[0].in_archive, 9)

    def test_machine_paths(self):
        ours = self.path("bin")
        os.makedirs(ours)
        theirs_here = self.path("their-bin")
        os.makedirs(theirs_here)
        set_app_setting("qemupath", ours)
        set_app_setting("vdepath", ours)
        data = project(
            settings={"qemupath": "/opt/qemu", "vdepath": theirs_here}
        )
        plan = plan_import(self.contents(data), self.workspace)
        self.assertEqual(
            plan.machine_paths,
            [
                MachinePath("qemupath", "/opt/qemu", ours, True),
                MachinePath("vdepath", theirs_here, ours, False),
            ],
        )
        data = project(settings={"qemupath": ours})
        self.assertEqual(
            plan_import(self.contents(data), self.workspace).machine_paths, []
        )
        data = {"format": 1, "settings": "odd"}
        self.assertEqual(
            plan_import(self.contents(data), self.workspace).machine_paths, []
        )

    def test_problems(self):
        plan = self.plan({"deb": "/gone"}, {"deb": 5})
        self.assertEqual(plan.problems(self.workspace), [])
        plan.name = ".lab"
        self.assertEqual(
            plan.problems(self.workspace), ["The name cannot start with a dot"]
        )
        plan.name = "lab"
        plan.images[0].choice = "use"
        plan.images[0].path = ""
        self.assertEqual(
            plan.problems(self.workspace), ['deb: "" doesn\'t exist']
        )

    def test_the_bricks_must_fit(self):
        self.patch(
            locations, "runtime_dir", lambda: "/run/user/1000/virtualbricks"
        )
        plan = self.plan({}, bricks={"b" * 19: {"type": "switch"}})
        plan.name = "x" * 40
        [problem] = plan.problems(self.workspace)
        self.assertIn("leaves 18 bytes", problem)

    def test_the_job(self):
        plan = self.plan(
            {"deb": "/gone", "late": "/gone"}, {"deb": 5}, complete=False
        )
        plan.machine_paths = [
            MachinePath("qemupath", "/opt", "/usr/bin", True),
            MachinePath("vdepath", "/opt", "/usr/bin", False),
        ]
        job = plan.job(self.workspace, "/ws/.importing-x", "/usr/bin/qemu-img")
        self.assertEqual(job["job"], "import")
        self.assertEqual(
            job["destination"], self.workspace.project_path("lab")
        )
        self.assertEqual(
            [(i["name"], i["choice"]) for i in job["images"]],
            [("deb", "copy"), ("late", "auto")],
        )
        self.assertEqual(job["settings"], {"qemupath": "/usr/bin"})
        # it goes through TOML
        dumps(job)


class TestRunImport(ImportingTestCase):

    def setUp(self):
        super().setUp()
        self.qemu_log = self.path("qemu-img.log")
        self.qemu_fail = self.path("qemu-img.fail")
        self.qemu_img = self.file(
            self.path("bin", "qemu-img"),
            FAKE_QEMU_IMG.format(
                log=self.qemu_log, fail=self.qemu_fail
            ).encode(),
        )
        os.chmod(self.qemu_img, 0o755)
        self.emitted = []

    def archive(self, data, files=None, legacy=False):
        members = {".project": LEGACY} if legacy else {}
        if data is not None:
            members["project.toml"] = dumps(data).encode()
        members.update(files or {})
        return make_archive(self.path("lab.vbp"), members)

    def lab(self, images=None):
        data = project(
            {"deb": "/other/deb.qcow2"},
            {"vm": vm(("hda", "deb"))},
            {"qemupath": "/opt/qemu"},
        )
        files = {"vm_hda.cow": b"cow", "README": b"A lab"}
        for name in images if images is not None else ["deb"]:
            files[f".images/{name}"] = b"image of " + name.encode()
        return self.archive(data, files)

    def plan(self, path):
        contents = archive.inspect(path, Tool("tarfile"), lambda obj: None)
        return plan_import(contents, self.workspace)

    def run_import(self, plan, tool=None, qemu_img=None):
        os.makedirs(self.workspace.path, exist_ok=True)
        staging = os.path.join(self.workspace.path, ".importing-lab-x")
        os.makedirs(staging)
        job = plan.job(
            self.workspace,
            staging,
            self.qemu_img if qemu_img is None else qemu_img,
        )
        result = archive.run_job(
            job, self.emitted.append, tool or Tool("tarfile")
        )
        return ImportResult.from_table(result)

    def qemu_calls(self):
        with open(self.qemu_log) as fp:
            return fp.read().splitlines()

    def data(self, name="lab"):
        return load_toml(self.workspace._project_file(name))

    def test_import(self):
        plan = self.plan(self.lab())
        set_app_setting("qemupath", "/usr/bin")
        plan.machine_paths[0].use_ours = True
        result = self.run_import(plan)
        self.assertEqual(result.name, "lab")
        self.assertEqual(list(result.report), [])
        self.assertEqual(self.workspace.names(), ["lab"])
        folder = self.workspace.project_path("lab")
        self.assertEqual(
            sorted(os.listdir(folder)),
            ["README", "project.toml", "vm_hda.cow"],
        )
        # the folder isn't private like a temporary one
        self.assertTrue(os.stat(folder).st_mode & stat.S_IROTH)
        image = os.path.join(self.library, "deb.qcow2")
        with open(image, "rb") as fp:
            self.assertEqual(fp.read(), b"image of deb")
        data = self.data()
        self.assertEqual(data["images"]["deb"]["path"], image)
        self.assertEqual(data["settings"]["qemupath"], "/usr/bin")
        cow = os.path.join(folder, "vm_hda.cow")
        staged = cow.replace(
            folder, os.path.join(self.workspace.path, ".importing-lab-x")
        )
        self.assertEqual(
            self.qemu_calls(),
            [
                f"info --output=json {image}",
                f"rebase -u -b {image} -F raw {staged}",
            ],
        )
        self.assertIn({"created": image}, self.emitted)

    def test_with_every_tool(self):
        path = self.lab()
        for name in ("bsdtar", "gnutar"):
            tool = TOOLS[name]
            if tool is None:  # pragma: no cover
                continue
            result = self.run_import(self.plan(path), Tool(name, tool))
            self.assertTrue(self.workspace.exists(result.name))
            os.rename(
                self.workspace.project_path(result.name),
                self.path(f"done-{name}"),
            )

    def test_use_a_file(self):
        mine = self.file(self.path("mine.qcow2"))
        plan = self.plan(self.lab())
        plan.images[0].choice = "use"
        plan.images[0].path = mine
        self.run_import(plan)
        self.assertEqual(self.data()["images"]["deb"]["path"], mine)
        self.assertEqual(os.listdir(self.library), [])
        self.assertIn(f"rebase -u -b {mine} -F raw", self.qemu_calls()[1])

    def test_leave_unset(self):
        plan = self.plan(self.lab())
        plan.images[0].choice = "skip"
        result = self.run_import(plan)
        self.assertEqual(self.data()["images"]["deb"]["path"], "")
        self.assertEqual(
            [m.where for m in result.report],
            ["images.deb", "bricks.vm.disks.hda"],
        )
        self.assertFalse(os.path.exists(self.qemu_log))

    def test_auto(self):
        mine = self.file(self.path("mine.qcow2"))
        data = project(
            {"deb": "/o/deb", "mine": mine, "gone": "/o/gone"},
        )
        path = self.archive(data, {".images/deb": b"deb"})
        contents = self.contents(data, complete=False, path=path)
        plan = plan_import(contents, self.workspace)
        self.assertEqual([i.known for i in plan.images], [False] * 3)
        self.run_import(plan)
        paths = {k: v["path"] for k, v in self.data()["images"].items()}
        self.assertEqual(
            paths,
            {
                "deb": os.path.join(self.library, "deb"),
                "mine": mine,
                "gone": "",
            },
        )

    def test_copy_what_the_archive_doesnt_have(self):
        plan = self.plan(self.lab(images=[]))
        plan.images[0].choice = "copy"
        plan.images[0].path = os.path.join(self.library, "deb.qcow2")
        result = self.run_import(plan)
        self.assertEqual(self.data()["images"]["deb"]["path"], "")
        self.assertIn("not in the archive", str(list(result.report)[0]))

    def test_the_copy_takes_a_free_name(self):
        plan = self.plan(self.lab())
        self.file(plan.images[0].path, b"arrived meanwhile")
        self.run_import(plan)
        self.assertEqual(
            self.data()["images"]["deb"]["path"],
            os.path.join(self.library, "deb.1.qcow2"),
        )

    def test_without_qemu_img(self):
        result = self.run_import(self.plan(self.lab()), qemu_img="")
        [message] = list(result.report)
        self.assertIn("qemu-img not found", message.text)

    def test_rebase_errors(self):
        self.file(self.qemu_fail)
        result = self.run_import(self.plan(self.lab()))
        [message] = list(result.report)
        self.assertIn("cannot rebase", message.text)
        missing = self.path("missing-qemu-img")
        result = self.run_import(self.plan(self.lab()), qemu_img=missing)
        self.assertIn("qemu-img", str(list(result.report)[0]))

    def test_an_archive_of_an_older_virtualbricks(self):
        path = self.archive(None, legacy=True)
        result = self.run_import(self.plan(path))
        self.assertEqual(self.data(result.name)["bricks"]["sw"]["numports"], 8)

    def test_no_project_file(self):
        plan = self.plan(self.lab())
        make_archive(plan.contents.path, {"README": b"x"})
        self.assertRaises(ArchiveError, self.run_import, plan)
        self.assertEqual(os.listdir(self.workspace.path), ["vimages"])

    def test_a_newer_project_file(self):
        plan = self.plan(self.lab())
        make_archive(plan.contents.path, {"project.toml": b"format = 9\n"})
        with self.assertRaises(ArchiveError) as cm:
            self.run_import(plan)
        self.assertIn("newer", str(cm.exception))

    def test_a_failure_removes_what_was_written(self):
        def fail(self, data, paths):
            raise OSError("disk full")

        self.patch(importing._Import, "rebase", fail)
        self.assertRaises(OSError, self.run_import, self.plan(self.lab()))
        self.assertEqual(os.listdir(self.workspace.path), ["vimages"])
        self.assertEqual(os.listdir(self.library), [])

    def test_a_project_appeared_meanwhile(self):
        plan = self.plan(self.lab())
        self.workspace.create("lab")
        result = self.run_import(plan)
        self.assertEqual(result.name, "lab-2")
        self.assertIn('imported as "lab-2"', list(result.report)[0].text)

    def test_the_holes_come_back_without_bsdtar(self):
        disk = sparse_file(self.path("vm_hda.cow"), 8 * MiB)
        path = self.path("lab.vbp")
        with tarfile.open(path, "w:gz") as tar:
            add(tar, "project.toml", dumps(project()).encode())
            tar.add(disk, "vm_hda.cow")
            add(tar, "notes", bytes(2 * MiB))
        result = self.run_import(self.plan(path))
        folder = self.workspace.project_path(result.name)
        cow = os.path.join(folder, "vm_hda.cow")
        self.assertEqual(os.path.getsize(cow), 8 * MiB)
        self.assertLess(os.stat(cow).st_blocks * 512, MiB)
        # only the disks
        notes = os.path.join(folder, "notes")
        self.assertGreaterEqual(os.stat(notes).st_blocks * 512, 2 * MiB)


class TestImportProject(ImportingTestCase):

    def test_the_job_runs_in_the_process(self):
        spawned = []

        class Reactor:
            def spawnProcess(self, protocol, executable, args, env):
                spawned.append(protocol)

        plan = plan_import(self.contents(project()), self.workspace)
        job = importing.import_project(
            plan, self.workspace, qemu_img="/q", reactor=Reactor()
        )
        [staging] = job.leftovers
        self.assertTrue(
            os.path.basename(staging).startswith(".importing-lab-")
        )
        self.assertEqual(os.path.dirname(staging), self.workspace.path)
        self.assertEqual(job.job["staging"], staging)
        self.assertEqual(job.job["qemu_img"], "/q")
        self.assertEqual(spawned, [job.protocol])
        # the list of projects ignores it
        self.assertEqual(self.workspace.names(), [])
        job.message(
            {"result": {"name": "lab", "report": [["info", "hi", ""]]}}
        )
        job.ended("")
        result = self.successResultOf(job.done)
        self.assertEqual(result.name, "lab")
        self.assertEqual([m.text for m in result.report], ["hi"])

    def test_image_use_defaults(self):
        image = ImageUse("deb", [], "/o/deb", None)
        self.assertEqual((image.choice, image.known), ("skip", True))
