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

"""The disk images: what qemu-img info says, who uses them, relinking."""

import json
import os

from twisted.internet import defer

from virtualbricks import errors
from virtualbricks.config import images
from virtualbricks.config.images import (
    ImageInfo,
    InfoCache,
    RunningError,
    parse_info,
    read_info,
    relink,
    uses,
)
from virtualbricks.config.workspace import OpenProject
from virtualbricks.tests import BrickTestCase, FakeLogger, use_workspace

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
            qemu_img.calls, [["info", "--output=json", "/lab/frr.qcow2"]]
        )

    def test_read_info_with_qemu_img(self):
        # the qemu-img of spawn, when none is given
        qemu_img = FakeQemuImg()
        qemu_img.infos["/lab/frr.qcow2"] = INFO
        self.patch(images.spawn, "qemu_img", qemu_img)
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
        self.image = self.factory.new_disk_image("frr", "/lab/frr.qcow2")
        self.qemu_img = FakeQemuImg()
        self.qemu_img.infos["/new/frr.qcow2"] = dict(INFO, format="qcow2")

    def vm(self, name, device="hda", private=True, image=None):
        vm = self.factory.new_brick("qemu", name)
        vm.set(
            {
                device: (image or self.image).get_name(),
                "private" + device: private,
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
        other = self.factory.new_disk_image("debian", "/lab/debian.raw")
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
        self.assertEqual(self.image.get_path(), "/new/frr.qcow2")
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
        self.assertEqual(self.image.get_path(), os.path.abspath("frr.qcow2"))

    def test_the_same_path(self):
        self.copy(self.vm("r1"))
        self.successResultOf(self.relink("/lab/frr.qcow2"))
        self.assertEqual(self.qemu_img.calls, [])

    def test_the_path_of_another_image(self):
        self.factory.new_disk_image("debian", "/new/frr.qcow2")
        self.failureResultOf(self.relink(), errors.ImageAlreadyInUseError)
        self.assertEqual(self.qemu_img.calls, [])
        self.assertEqual(self.image.get_path(), "/lab/frr.qcow2")

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
        self.assertEqual(self.image.get_path(), "/lab/frr.qcow2")

    def test_a_file_that_qemu_img_cant_read(self):
        self.copy(self.vm("r1"))
        self.qemu_img.failing.add(("info", "--output=json"))
        self.failureResultOf(self.relink(), RuntimeError)
        self.assertEqual(self.qemu_img.rebases(), [])
        self.assertEqual(self.image.get_path(), "/lab/frr.qcow2")

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
        self.assertEqual(self.image.get_path(), "/lab/frr.qcow2")
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
        self.patch(images.spawn, "qemu_img", self.qemu_img)
        self.copy(self.vm("r1"))
        self.successResultOf(
            relink(self.factory, self.image, "/new/frr.qcow2")
        )
        self.assertEqual(len(self.qemu_img.rebases()), 1)
