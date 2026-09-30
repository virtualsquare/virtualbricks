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
The disk images: what qemu-img info says, who uses them, relinking, the
image folder, the other projects that use a file, and the private copies.
"""

import json
import os

from twisted.internet import defer

from virtualbricks import errors
from virtualbricks.config import images
from virtualbricks.config.images import (
    ImageInfo,
    InfoCache,
    RunningError,
    adopt,
    discard,
    free_path,
    image_folder,
    is_inside,
    other_projects,
    parse_info,
    read_info,
    relink,
    start_over,
    uses,
)
from virtualbricks.config.workspace import (
    ImageSummary,
    OpenProject,
    ProjectSummary,
)
from virtualbricks.tests import (
    BrickTestCase,
    FakeLogger,
    FakeTrash,
    use_workspace,
)

INFO = {
    "virtual-size": 4000000000,
    "filename": "/lab/frr.qcow2",
    "format": "qcow2",
    "actual-size": 1900000000,
    "snapshots": [{"name": "virtualbricks", "id": "1"}],
}


class FakeQemuImg:
    """qemu-img: what it was asked, and the info of each file."""

    def __init__(self):
        self.calls = []
        self.infos = {}
        # the commands that fail, by their first arguments
        self.failing = set()
        # the commands that wait, until they are fired
        self.waiting = []

    def __call__(self, args):
        self.calls.append(args)
        if tuple(args[:2]) in self.failing or tuple(args[-1:]) in self.failing:
            return defer.fail(RuntimeError(f"qemu-img: {args[0]} failed"))
        if args[0] == "info":
            return defer.succeed(json.dumps(self.infos[args[-1]]))
        return defer.succeed("")

    def rebases(self):
        return [args for args in self.calls if args[0] == "rebase"]


class TestParseInfo(BrickTestCase):

    def test_an_image(self):
        info = parse_info(INFO)
        self.assertEqual(
            info,
            ImageInfo(
                format="qcow2",
                virtual_size=4000000000,
                actual_size=1900000000,
                backing_file=None,
                snapshots=("virtualbricks",),
            ),
        )

    def test_a_backing_file(self):
        # the full path, when qemu-img gives it
        info = parse_info(
            {
                "format": "qcow2",
                "backing-filename": "frr.qcow2",
                "full-backing-filename": "/lab/frr.qcow2",
            }
        )
        self.assertEqual(info.backing_file, "/lab/frr.qcow2")
        info = parse_info({"backing-filename": "frr.qcow2"})
        self.assertEqual(info.backing_file, "frr.qcow2")

    def test_what_is_missing(self):
        self.assertEqual(
            parse_info({}),
            ImageInfo(
                format="",
                virtual_size=0,
                actual_size=0,
                backing_file=None,
                snapshots=(),
            ),
        )

    def test_read_info(self):
        qemu_img = FakeQemuImg()
        qemu_img.infos["/lab/frr.qcow2"] = INFO
        info = self.successResultOf(read_info("/lab/frr.qcow2", qemu_img))
        self.assertEqual(info.format, "qcow2")
        self.assertEqual(
            qemu_img.calls, [["info", "--output=json", "-U", "/lab/frr.qcow2"]]
        )

    def test_read_info_with_qemu_img(self):
        # the qemu-img of qemu.run, when none is given
        qemu_img = FakeQemuImg()
        qemu_img.infos["/lab/frr.qcow2"] = INFO
        self.patch(images.qemu_run, "qemu_img", qemu_img)
        self.successResultOf(read_info("/lab/frr.qcow2"))
        self.assertEqual(len(qemu_img.calls), 1)


class TestInfoCache(BrickTestCase):

    def setUp(self):
        super().setUp()
        self.qemu_img = FakeQemuImg()
        self.path = os.path.abspath(self.mktemp())
        self.write(b"disk")
        self.qemu_img.infos[self.path] = INFO
        self.cache = InfoCache(self.qemu_img)

    def write(self, data, mtime=None):
        with open(self.path, "wb") as fp:
            fp.write(data)
        if mtime is not None:
            os.utime(self.path, (mtime, mtime))

    def test_read_once(self):
        self.assertIsNone(self.cache.get(self.path))
        info = self.successResultOf(self.cache.read(self.path))
        self.assertEqual(info.virtual_size, 4000000000)
        self.assertIs(self.cache.get(self.path), info)
        self.assertIs(self.successResultOf(self.cache.read(self.path)), info)
        self.assertEqual(len(self.qemu_img.calls), 1)

    def test_read_again_when_the_file_changes(self):
        self.write(b"disk", mtime=1000)
        self.successResultOf(self.cache.read(self.path))
        # the same size, another time
        self.write(b"disk", mtime=2000)
        self.assertIsNone(self.cache.get(self.path))
        self.successResultOf(self.cache.read(self.path))
        # the same time, another size
        self.write(b"bigger disk", mtime=2000)
        self.assertIsNone(self.cache.get(self.path))
        self.successResultOf(self.cache.read(self.path))
        self.assertEqual(len(self.qemu_img.calls), 3)

    def test_one_read_for_all_who_ask(self):
        running = defer.Deferred()
        self.patch(images, "read_info", lambda path, run: running)
        first = self.cache.read(self.path)
        second = self.cache.read(self.path)
        self.assertNoResult(first)
        running.callback(parse_info(INFO))
        self.assertIs(
            self.successResultOf(first), self.successResultOf(second)
        )

    def test_a_missing_file(self):
        os.remove(self.path)
        self.failureResultOf(self.cache.read(self.path), OSError)
        self.assertIsNone(self.cache.get(self.path))
        self.assertEqual(self.qemu_img.calls, [])

    def test_a_file_gone_after_it_was_read(self):
        self.successResultOf(self.cache.read(self.path))
        os.remove(self.path)
        self.assertIsNone(self.cache.get(self.path))

    def test_a_failure_is_not_kept(self):
        self.qemu_img.failing.add(("info", "--output=json"))
        first = self.cache.read(self.path)
        self.failureResultOf(first, RuntimeError)
        self.assertIsNone(self.cache.get(self.path))
        self.qemu_img.failing.clear()
        self.successResultOf(self.cache.read(self.path))


class ImagesTestCase(BrickTestCase):
    """A project open, with an image and machines that use it."""

    def setUp(self):
        super().setUp()
        self.projects = use_workspace(self, self.mktemp())
        self.projects.current = OpenProject(
            os.path.abspath(self.mktemp()), None
        )
        os.makedirs(self.projects.current.path)
        self.image = self.factory.new_image("frr", "/lab/frr.qcow2")
        self.qemu_img = FakeQemuImg()
        self.qemu_img.infos["/new/frr.qcow2"] = dict(INFO, format="qcow2")

    def vm(self, name, device="hda", private=True, image=None):
        vm = self.factory.new_brick("qemu", name)
        vm.update_config(
            {
                f"{device}_image": (image or self.image).name,
                f"{device}_private": private,
            }
        )
        return vm

    def copy(self, vm, device="hda", data=b"changes"):
        """Make the private copy of a disk, as its machine's first start."""

        path = vm.disk(device).get_cow_path()
        with open(path, "wb") as fp:
            fp.write(data)
        return path

    def running(self, vm):
        vm.__isrunning__ = lambda: True
        return vm


class TestUses(ImagesTestCase):

    def test_the_disks(self):
        r1 = self.vm("r1")
        r2 = self.running(self.vm("r2", "hdb", private=False))
        other = self.factory.new_image("debian", "/lab/debian.raw")
        self.vm("vm", image=other)
        copy = self.copy(r1)
        found = uses(self.factory, self.image)
        self.assertEqual(
            [(use.vm, use.device, use.private, use.running) for use in found],
            [(r1, "hda", True, False), (r2, "hdb", False, True)],
        )
        self.assertEqual(found[0].copy, copy)
        self.assertEqual(found[0].copy_size, os.stat(copy).st_blocks * 512)
        # the image itself: no copy
        self.assertIsNone(found[1].copy)
        self.assertIsNone(found[1].copy_size)

    def test_a_copy_not_made_yet(self):
        r1 = self.vm("r1")
        [use] = uses(self.factory, self.image)
        self.assertEqual(use.copy, r1.disk("hda").get_cow_path())
        self.assertIsNone(use.copy_size)

    def test_no_disk(self):
        self.factory.new_brick("switch", "sw")
        self.assertEqual(uses(self.factory, self.image), [])

    def test_while_no_project_is_open(self):
        # as while a project loads: its folder isn't known yet
        self.projects.current = None
        self.vm("r1")
        [use] = uses(self.factory, self.image)
        self.assertTrue(use.private)
        self.assertIsNone(use.copy)
        self.assertIsNone(use.copy_size)


class TestRelink(ImagesTestCase):

    def relink(self, path="/new/frr.qcow2"):
        return relink(self.factory, self.image, path, self.qemu_img)

    def test_the_private_copies_first(self):
        r1, r2, r3 = self.vm("r1"), self.vm("r2"), self.vm("r3")
        self.vm("vm", "hdb", private=False)
        copies = [self.copy(r1), self.copy(r3)]
        changes = []
        self.image.changed.connect(
            lambda image: changes.append(len(self.qemu_img.rebases()))
        )
        self.successResultOf(self.relink())
        self.assertEqual(
            self.qemu_img.rebases(),
            [
                ["rebase", "-u", "-b", "/new/frr.qcow2", "-F", "qcow2", copy]
                for copy in copies
            ],
        )
        self.assertEqual(self.image.path, "/new/frr.qcow2")
        # the path changes once the copies point at it
        self.assertEqual(changes, [2])
        # r2's copy isn't made yet: its first start makes it on the new file
        self.assertNotIn(r2.disk("hda").get_cow_path(), copies)

    def test_in_the_format_of_the_new_file(self):
        self.qemu_img.infos["/new/frr.raw"] = dict(INFO, format="raw")
        self.copy(self.vm("r1"))
        self.successResultOf(self.relink("/new/frr.raw"))
        [rebase] = self.qemu_img.rebases()
        self.assertEqual(rebase[4:6], ["-F", "raw"])

    def test_a_relative_path(self):
        self.qemu_img.infos[os.path.abspath("frr.qcow2")] = INFO
        self.successResultOf(self.relink("frr.qcow2"))
        self.assertEqual(self.image.path, os.path.abspath("frr.qcow2"))

    def test_the_same_path(self):
        self.copy(self.vm("r1"))
        self.successResultOf(self.relink("/lab/frr.qcow2"))
        self.assertEqual(self.qemu_img.calls, [])

    def test_the_path_of_another_image(self):
        self.factory.new_image("debian", "/new/frr.qcow2")
        self.failureResultOf(self.relink(), errors.ImageAlreadyInUseError)
        self.assertEqual(self.qemu_img.calls, [])
        self.assertEqual(self.image.path, "/lab/frr.qcow2")

    def test_not_while_a_machine_runs(self):
        self.copy(self.vm("r1"))
        self.running(self.vm("r3"))
        self.running(self.vm("r2", private=False))
        failure = self.failureResultOf(self.relink(), RunningError)
        self.assertEqual(failure.value.names, ["r2", "r3"])
        self.assertEqual(
            failure.getErrorMessage(),
            "stop the machines that use it first: r2, r3",
        )
        self.assertEqual(self.qemu_img.calls, [])
        self.assertEqual(self.image.path, "/lab/frr.qcow2")

    def test_a_file_that_qemu_img_cant_read(self):
        self.copy(self.vm("r1"))
        self.qemu_img.failing.add(("info", "--output=json"))
        self.failureResultOf(self.relink(), RuntimeError)
        self.assertEqual(self.qemu_img.rebases(), [])
        self.assertEqual(self.image.path, "/lab/frr.qcow2")

    def test_a_copy_that_cant_be_pointed(self):
        # the copies already pointed go back, and the image keeps its file
        logger = FakeLogger()
        self.patch(images, "logger", logger)
        first, second = self.copy(self.vm("r1")), self.copy(self.vm("r2"))
        self.qemu_img.failing.add((second,))
        self.failureResultOf(self.relink(), RuntimeError)
        self.assertEqual(
            self.qemu_img.rebases(),
            [
                ["rebase", "-u", "-b", "/new/frr.qcow2", "-F", "qcow2", first],
                [
                    "rebase",
                    "-u",
                    "-b",
                    "/new/frr.qcow2",
                    "-F",
                    "qcow2",
                    second,
                ],
                ["rebase", "-u", "-b", "/lab/frr.qcow2", "-F", "qcow2", first],
            ],
        )
        self.assertEqual(self.image.path, "/lab/frr.qcow2")
        self.assertEqual(logger.events, [])

    def test_a_copy_that_cant_go_back(self):
        logger = FakeLogger()
        self.patch(images, "logger", logger)
        first = self.copy(self.vm("r1"))
        second = self.copy(self.vm("r2"))
        self.qemu_img.failing.add((second,))
        failing = self.qemu_img.__call__

        def back_fails(args):
            if args[:4] == ["rebase", "-u", "-b", "/lab/frr.qcow2"]:
                return defer.fail(RuntimeError("read-only"))
            return failing(args)

        relinked = relink(
            self.factory, self.image, "/new/frr.qcow2", back_fails
        )
        self.failureResultOf(relinked, RuntimeError)
        self.assertEqual(logger.levels(), ["failure"])
        self.assertEqual(
            logger.formatted(),
            [
                f"Cannot point {first} back at /lab/frr.qcow2: its machine"
                " will start from an empty private copy"
            ],
        )

    def test_with_qemu_img(self):
        self.patch(images.qemu_run, "qemu_img", self.qemu_img)
        self.copy(self.vm("r1"))
        self.successResultOf(
            relink(self.factory, self.image, "/new/frr.qcow2")
        )
        self.assertEqual(len(self.qemu_img.rebases()), 1)


class TestFiles(BrickTestCase):

    def test_the_image_folder(self):
        workspace = use_workspace(self, os.path.abspath(self.mktemp()))
        folder = image_folder(workspace)
        self.assertEqual(folder, os.path.join(workspace.path, "vimages"))
        self.assertTrue(os.path.isdir(folder))
        # made once
        self.assertEqual(image_folder(workspace), folder)

    def test_inside(self):
        self.assertTrue(is_inside("/ws/vimages/frr.qcow2", "/ws/vimages"))
        self.assertTrue(is_inside("/ws/vimages/old/frr.qcow2", "/ws/vimages"))
        self.assertTrue(is_inside("/ws/vimages/../vimages/a", "/ws/vimages/"))

    def test_outside(self):
        self.assertFalse(is_inside("/ws/vimages2/frr.qcow2", "/ws/vimages"))
        self.assertFalse(is_inside("/ws/vimages/../frr.qcow2", "/ws/vimages"))
        self.assertFalse(is_inside("/tmp/frr.qcow2", "/ws/vimages"))

    def test_a_free_path(self):
        folder = self.mktemp()
        os.makedirs(folder)
        self.assertEqual(
            free_path(folder, "frr.qcow2"), os.path.join(folder, "frr.qcow2")
        )

    def test_a_number_when_taken(self):
        folder = self.mktemp()
        os.makedirs(folder)
        for name in ("frr.qcow2", "frr-2.qcow2"):
            open(os.path.join(folder, name), "w").close()
        # a broken link takes a name too
        os.symlink("/nowhere", os.path.join(folder, "frr-3.qcow2"))
        self.assertEqual(
            free_path(folder, "frr.qcow2"),
            os.path.join(folder, "frr-4.qcow2"),
        )


class FakeWorkspace:
    """The summaries of the projects, and the open one."""

    def __init__(self, current, **projects):
        self.current = OpenProject("/ws/" + current, None) if current else None
        self._summaries = [
            ProjectSummary(
                name=name,
                path="/ws/" + name,
                description="",
                modified=0.0,
                bricks={},
                events=0,
                images=tuple(
                    ImageSummary(image, path, True) for image, path in images
                ),
            )
            for name, images in projects.items()
        ]

    def summaries(self):
        return self._summaries


class TestOtherProjects(BrickTestCase):

    def test_the_projects_that_use_the_file(self):
        workspace = FakeWorkspace(
            "lab",
            lab=[("frr", "/ws/vimages/frr.qcow2")],
            ospf=[("router", "/ws/vimages/frr.qcow2"), ("pc", "/ws/pc.img")],
            bgp=[("pc", "/ws/pc.img")],
            rip=[("r", "/ws/vimages/../vimages/frr.qcow2"), ("empty", "")],
        )
        self.assertEqual(
            other_projects(workspace, "/ws/vimages/frr.qcow2"),
            [("ospf", "router"), ("rip", "r")],
        )

    def test_none(self):
        workspace = FakeWorkspace("lab", lab=[("frr", "/ws/frr.qcow2")])
        self.assertEqual(other_projects(workspace, "/ws/frr.qcow2"), [])

    def test_no_project_open(self):
        workspace = FakeWorkspace(None, lab=[("frr", "/ws/frr.qcow2")])
        self.assertEqual(
            other_projects(workspace, "/ws/frr.qcow2"), [("lab", "frr")]
        )


class TestPrivateCopies(ImagesTestCase):

    def test_discard_to_the_trash(self):
        path = self.copy(self.vm("r1"))
        trash = FakeTrash()
        self.assertTrue(discard(path, trash))
        self.assertEqual(trash.trashed, [path])

    def test_discard_without_a_trash(self):
        path = self.copy(self.vm("r1"))
        self.assertFalse(discard(path, FakeTrash(can_trash=False)))
        self.assertFalse(os.path.exists(path))
        path = self.copy(self.vm("r2"))
        self.assertFalse(discard(path))
        self.assertFalse(os.path.exists(path))

    def test_discard_a_file_gone(self):
        trash = FakeTrash()
        self.assertFalse(discard("/nowhere/r1_hda.cow", trash))
        self.assertEqual(trash.asked, [])

    def test_start_over(self):
        vm = self.vm("r1")
        path = self.copy(vm)
        trash = FakeTrash()
        self.assertTrue(start_over(vm, "hda", trash))
        self.assertEqual(trash.trashed, [path])
        # the disk keeps its image and its mode
        self.assertIs(vm.disk("hda").image, self.image)
        self.assertTrue(vm.disk("hda").is_cow())

    def test_not_while_it_runs(self):
        vm = self.running(self.vm("r1"))
        path = self.copy(vm)
        with self.assertRaises(RunningError) as cm:
            start_over(vm, "hda")
        self.assertEqual(cm.exception.names, ["r1"])
        self.assertTrue(os.path.exists(path))

    def test_adopt(self):
        vm = self.vm("r1")
        path = self.copy(vm)
        trash = FakeTrash()
        image = adopt(
            self.factory, vm, "hda", "frr-r1", "/lab/frr-r1.qcow2", True, trash
        )
        self.assertIs(self.factory.get_image("frr-r1"), image)
        self.assertEqual(image.path, "/lab/frr-r1.qcow2")
        self.assertIs(vm.disk("hda").image, image)
        # its changes are in the image now
        self.assertEqual(trash.trashed, [path])

    def test_adopt_only(self):
        vm = self.vm("r1")
        path = self.copy(vm)
        image = adopt(
            self.factory, vm, "hda", "frr-r1", "/lab/frr-r1.qcow2", False
        )
        self.assertIsNotNone(image)
        self.assertIs(vm.disk("hda").image, self.image)
        self.assertTrue(os.path.exists(path))
