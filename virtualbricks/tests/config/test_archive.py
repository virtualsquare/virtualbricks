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

"""The archive process: tools, reading, extracting, the protocol."""

import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile

from twisted.internet import error
from twisted.python import failure
from twisted.trial import unittest

from virtualbricks.config import archive
from virtualbricks.config.tomlfile import dumps_toml
from virtualbricks.config.archive import (
    ArchiveContents,
    ArchiveError,
    ArchiveJob,
    Member,
    Tool,
)
from virtualbricks.config.report import Report

MiB = 1 << 20
PROJECT = dumps_toml(
    {
        "format": 1,
        "settings": {},
        "images": {"deb": {"path": "/srv/deb.qcow2"}},
        "bricks": {"sw": {"type": "switch"}},
    }
).encode()
LEGACY = b"[Switch:sw]\nnumports=8\n"
TOOLS = {
    "bsdtar": shutil.which("bsdtar"),
    "gnutar": shutil.which("tar"),
}


def make_archive(path, files, mode="w:gz", contents=None):
    """
    Write an archive of files, name -> bytes, in their order.

    With contents, a list of the members, contents.toml comes first.
    """

    with tarfile.open(path, mode, format=tarfile.PAX_FORMAT) as tar:
        if contents is not None:
            text = archive.write_contents(contents).encode()
            add(tar, archive.CONTENTS, text)
        for name, data in files.items():
            add(tar, name, data)
    return path


def add(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def sparse_file(path, size, data=b"data"):
    with open(path, "wb") as fp:
        fp.write(data)
        fp.truncate(size)
    return path


class Emitted(list):
    def __call__(self, obj):
        self.append(obj)

    def of(self, key):
        return [obj[key] for obj in self if key in obj]


class ArchiveTestCase(unittest.TestCase):

    def setUp(self):
        self.root = os.path.abspath(self.mktemp())
        os.makedirs(self.root)
        self.emitted = Emitted()

    def path(self, *segments):
        return os.path.join(self.root, *segments)

    def script(self, name, body):
        """A shell script, as a fake tool, in the folder bin."""

        path = self.path("bin", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fp:
            fp.write("#!/bin/sh\n" + body)
        os.chmod(path, 0o755)
        return path

    def assertStopped(self, pid_file):
        """The process whose pid is in pid_file is gone."""

        with open(pid_file) as fp:
            pid = int(fp.read())
        self.assertRaises(ProcessLookupError, os.kill, pid, 0)

    def tool(self, name):
        if name == "tarfile":
            return Tool("tarfile")
        path = TOOLS[name]
        if path is None:  # pragma: no cover
            raise unittest.SkipTest(f"{name} isn't installed")
        if name == "gnutar":
            found = archive.find_tool(
                which=lambda n: None if n == "bsdtar" else path
            )
            if found.name != "gnutar":  # pragma: no cover
                raise unittest.SkipTest("tar isn't GNU tar")
        return Tool(name, path)


class TestTools(unittest.TestCase):

    def test_bsdtar_first(self):
        which = {"bsdtar": "/usr/bin/bsdtar", "tar": "/usr/bin/tar"}.get
        self.assertEqual(
            archive.find_tool(which), Tool("bsdtar", "/usr/bin/bsdtar")
        )

    def run_version(self, stdout):
        class Result:
            pass

        def run(args, **kwargs):
            result = Result()
            result.stdout = stdout
            return result

        return run

    def test_gnu_tar(self):
        which = {"tar": "/bin/tar"}.get
        run = self.run_version("tar (GNU tar) 1.35\nCopyright\n")
        self.assertEqual(
            archive.find_tool(which, run), Tool("gnutar", "/bin/tar")
        )

    def test_busybox_tar_is_not_enough(self):
        which = {"tar": "/bin/tar"}.get
        run = self.run_version("tar (busybox) 1.36.1\n")
        self.assertEqual(archive.find_tool(which, run), Tool("tarfile"))

    def test_tar_that_cannot_run(self):
        def run(args, **kwargs):
            raise OSError("exec format error")

        self.assertEqual(
            archive.find_tool({"tar": "/bin/tar"}.get, run), Tool("tarfile")
        )

    def test_nothing_installed(self):
        self.assertEqual(archive.find_tool(lambda name: None), Tool("tarfile"))


class TestMembers(unittest.TestCase):

    def test_kinds(self):
        kind = archive.member_kind
        self.assertEqual(kind("contents.toml"), "contents")
        self.assertEqual(kind("./project.toml"), "project")
        self.assertEqual(kind(".project"), "legacy project")
        self.assertEqual(kind(".project~"), "legacy project")
        self.assertEqual(kind("README.md"), "readme")
        self.assertEqual(kind("README"), "readme")
        self.assertEqual(kind(".images/deb"), "image")
        self.assertEqual(kind(".images/a/b"), "other")
        self.assertEqual(kind("vm_hda.cow"), "disk")
        self.assertEqual(kind("sub/vm_hda.cow"), "other")
        self.assertEqual(kind("notes.txt"), "other")
        self.assertEqual(Member(".images/deb", 1, "image").image, "deb")

    def test_normalize(self):
        self.assertEqual(archive.normalize("././a/"), "a")

    def test_contents_round_trip(self):
        members = [
            Member("project.toml", 10, "project"),
            Member(".images/deb", 5, "image"),
        ]
        text = archive.write_contents(members).encode()
        self.assertEqual(archive.read_contents(text), members)

    def test_bad_contents(self):
        self.assertRaises(ArchiveError, archive.read_contents, b"[x")
        self.assertRaises(ArchiveError, archive.read_contents, b"\xff")
        self.assertRaises(ArchiveError, archive.read_contents, b"format = 2\n")
        members = archive.read_contents(
            b'format = 1\nmembers = [1, {name = "a", size = "x"}]\n'
        )
        self.assertEqual(members, [Member("a", 0, "other")])

    def test_contents_as_a_table(self):
        report = Report()
        report.warning("text", "where")
        contents = ArchiveContents(
            "/a.vbp",
            {"format": 1},
            "A lab",
            [Member(".images/deb", 5, "image")],
            True,
            report,
            converted=True,
        )
        table = json.loads(json.dumps(contents.to_table()))
        again = ArchiveContents.from_table(table)
        self.assertEqual(again.members, contents.members)
        self.assertEqual(list(again.report), list(report))
        self.assertTrue(again.converted)
        self.assertEqual(again.images, {"deb": contents.members[0]})
        self.assertEqual(again.size, 5)


class TestInspect(ArchiveTestCase):

    def inspect(self, path, tool="tarfile"):
        return archive.inspect(path, Tool(tool), self.emitted)

    def test_a_new_archive_is_read_up_to_its_head(self):
        members = [
            Member("project.toml", len(PROJECT), "project"),
            Member("README", 5, "readme"),
            Member(".images/deb", 8 * MiB, "image"),
        ]
        path = make_archive(
            self.path("lab.vbp"),
            {
                "project.toml": PROJECT,
                "README": b"A lab",
                ".images/deb": os.urandom(8 * MiB),
            },
            mode="w",
            contents=members,
        )
        contents = self.inspect(path)
        self.assertTrue(contents.complete)
        self.assertEqual(contents.members, members)
        self.assertEqual(contents.description, "A lab")
        self.assertEqual(contents.data["bricks"], {"sw": {"type": "switch"}})
        self.assertEqual(self.emitted.of("head"), [])
        # it stopped before the image
        done = max(p["done"] for p in self.emitted.of("progress"))
        self.assertLess(done, MiB)

    def test_an_archive_without_contents(self):
        path = make_archive(
            self.path("lab.vbp"),
            {
                "project.toml": PROJECT,
                "vm_hda.cow": b"x" * 100,
                "README": b"A lab",
                ".images/deb": b"y" * 50,
            },
        )
        contents = self.inspect(path)
        self.assertTrue(contents.complete)
        self.assertEqual(
            contents.members,
            [
                Member("project.toml", len(PROJECT), "project"),
                Member("vm_hda.cow", 100, "disk"),
                Member("README", 5, "readme"),
                Member(".images/deb", 50, "image"),
            ],
        )
        self.assertEqual(contents.description, "A lab")
        # the head as soon as the project file was read
        [head] = self.emitted.of("head")
        head = ArchiveContents.from_table(head)
        self.assertFalse(head.complete)
        self.assertEqual(head.members, contents.members[:1])
        self.assertEqual(head.data, contents.data)
        progress = self.emitted.of("progress")[-1]
        self.assertEqual(progress["done"], progress["total"])
        self.assertEqual(progress["step"], "read")

    def test_an_archive_of_an_older_virtualbricks(self):
        path = make_archive(self.path("lab.vbp"), {".project": LEGACY})
        contents = self.inspect(path)
        self.assertTrue(contents.converted)
        self.assertEqual(contents.data["bricks"]["sw"]["ports"], 8)

    def test_every_compression(self):
        for mode in ("w", "w:gz", "w:bz2", "w:xz"):
            path = make_archive(
                self.path(f"lab-{mode[2:]}.vbp"),
                {"project.toml": PROJECT},
                mode=mode,
            )
            self.assertEqual(self.inspect(path).members[0].kind, "project")

    def test_directories_are_not_members(self):
        path = self.path("lab.vbp")
        with tarfile.open(path, "w") as tar:
            info = tarfile.TarInfo("sub")
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
            add(tar, "project.toml", PROJECT)
        self.assertEqual(len(self.inspect(path).members), 1)

    def test_errors(self):
        self.assertRaises(ArchiveError, self.inspect, self.path("gone.vbp"))
        with open(self.path("text.vbp"), "w") as fp:
            fp.write("not an archive")
        self.assertRaises(ArchiveError, self.inspect, self.path("text.vbp"))
        path = make_archive(self.path("empty.vbp"), {"README": b"x"})
        with self.assertRaises(ArchiveError) as cm:
            self.inspect(path)
        self.assertIn("no project file", str(cm.exception))

    def test_bad_project_files(self):
        for name, data, text in (
            ("bad", b"[bricks\n", "project.toml"),
            ("utf", b"\xff", "project.toml"),
            ("newer", b"format = 9\n", "newer Virtualbricks"),
            ("legacy", b"\xff\xfe[", "can't be converted"),
        ):
            member = ".project" if name == "legacy" else "project.toml"
            path = make_archive(self.path(f"{name}.vbp"), {member: data})
            with self.assertRaises(ArchiveError) as cm:
                self.inspect(path)
            self.assertIn(text, str(cm.exception))

    def test_the_tools_read_the_archive_tarfile_would_misread(self):
        path = make_archive(
            self.path("lab.vbp"),
            {"project.toml": PROJECT, "README": b"A lab", "vm_hda.cow": b"x"},
        )
        self.patch(archive, "is_misread_sparse", lambda info: True)
        with self.assertRaises(archive.ToolNeeded):
            self.inspect(path)
        for name in ("bsdtar", "gnutar"):
            contents = archive.inspect(path, self.tool(name), self.emitted)
            self.assertEqual(contents.description, "A lab")
            self.assertEqual(
                [m.name for m in contents.members],
                ["project.toml", "README", "vm_hda.cow"],
            )

    def test_misread_sparse(self):
        info = tarfile.TarInfo("disk")
        self.assertFalse(archive.is_misread_sparse(info))
        info.pax_headers = {"GNU.sparse.major": "1", "size": "9000000000"}
        self.assertTrue(archive.is_misread_sparse(info))
        info.pax_headers = {"GNU.sparse.major": "1"}
        self.assertFalse(archive.is_misread_sparse(info))

    def test_listings(self):
        bsdtar = (
            "drwxr-xr-x  0 marco  marco       0 Sep 25 11:08 lab/\n"
            "-rw-r--r--  0 marco  marco      11 Sep 25 11:08 project.toml\n"
            "-rw-r--r--  0 marco  marco    4096 Sep 25  2025 my disk.cow\n"
            "lrwxrwxrwx  0 marco  marco       0 Sep 25 11:08 l -> x\n"
            "-rw-r--r--  0 marco  marco    many Sep 25 11:08 odd\n"
        )
        self.assertEqual(
            archive.parse_listing(bsdtar, 8),
            [
                Member("project.toml", 11, "project"),
                Member("my disk.cow", 4096, "other"),
            ],
        )
        gnutar = (
            "-rw-r--r-- marco/marco  101 2026-09-25 11:08 ./vm_hda.cow\n"
            "short line\n"
        )
        self.assertEqual(
            archive.parse_listing(gnutar, 5),
            [Member("vm_hda.cow", 101, "disk")],
        )

    def test_tool_errors(self):
        tool = self.tool("bsdtar")
        self.assertRaises(
            ArchiveError, archive.list_with_tool, tool, self.path("gone.vbp")
        )
        self.assertRaises(
            ArchiveError,
            archive.list_with_tool,
            Tool("bsdtar", self.path("no-such-tool")),
            self.path("gone.vbp"),
        )


class TestExtract(ArchiveTestCase):

    def lab(self):
        disk = sparse_file(self.path("vm_hda.cow"), 32 * MiB)
        path = self.path("lab.vbp")
        with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            add(tar, "project.toml", PROJECT)
            # tarfile doesn't record holes: they're zeros in the archive
            tar.add(disk, "vm_hda.cow")
            add(tar, ".images/deb", b"image")
        return path

    def extract(self, tool_name):
        path = self.lab()
        destination = self.path(f"out-{tool_name}")
        os.makedirs(destination)
        archive.extract(path, destination, self.tool(tool_name), self.emitted)
        return destination

    def check(self, destination):
        disk = os.path.join(destination, "vm_hda.cow")
        self.assertEqual(os.path.getsize(disk), 32 * MiB)
        with open(disk, "rb") as fp:
            self.assertEqual(fp.read(5), b"data\0")
        with open(os.path.join(destination, ".images", "deb"), "rb") as fp:
            self.assertEqual(fp.read(), b"image")
        progress = self.emitted.of("progress")[-1]
        self.assertEqual(progress["step"], "extract")
        self.assertEqual(progress["done"], progress["total"])

    def test_bsdtar_restores_the_holes(self):
        destination = self.extract("bsdtar")
        self.check(destination)
        disk = os.path.join(destination, "vm_hda.cow")
        self.assertLess(os.stat(disk).st_blocks * 512, MiB)

    def test_gnutar(self):
        self.check(self.extract("gnutar"))

    def test_tarfile(self):
        self.check(self.extract("tarfile"))

    def test_gnutar_needs_the_compression(self):
        for mode, flag in (
            ("w:gz", "--gzip"),
            ("w:bz2", "--bzip2"),
            ("w:xz", "--xz"),
            ("w", None),
        ):
            path = make_archive(self.path(f"a{mode[2:]}"), {"a": b"x"}, mode)
            self.assertEqual(
                archive.compression_flags(path), [flag] if flag else []
            )

    def test_unsafe_members_are_skipped_by_tarfile(self):
        path = self.path("evil.vbp")
        with tarfile.open(path, "w") as tar:
            add(tar, "../outside", b"x")
            add(tar, "/etc/absolute", b"x")
            link = tarfile.TarInfo("link")
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            tar.addfile(link)
            add(tar, "project.toml", PROJECT)
        destination = self.path("out")
        os.makedirs(destination)
        archive.extract(path, destination, Tool("tarfile"), self.emitted)
        self.assertFalse(os.path.exists(self.path("outside")))
        names = sorted(os.listdir(destination))
        self.assertIn("project.toml", names)
        self.assertNotIn("link", names)

    def test_the_fallback_filter(self):
        self.patch(tarfile, "data_filter", None)
        safe = archive._safe_member
        self.assertIsNone(safe(tarfile.TarInfo("../x"), "/d"))
        self.assertIsNone(safe(tarfile.TarInfo("/x"), "/d"))
        link = tarfile.TarInfo("l")
        link.type = tarfile.SYMTYPE
        self.assertIsNone(safe(link, "/d"))
        info = tarfile.TarInfo("ok")
        self.assertIs(safe(info, "/d"), info)

    def test_tool_errors(self):
        with open(self.path("text.vbp"), "w") as fp:
            fp.write("not an archive" * 100)
        destination = self.path("out")
        os.makedirs(destination)
        for name in ("bsdtar", "gnutar", "tarfile"):
            self.assertRaises(
                ArchiveError,
                archive.extract,
                self.path("text.vbp"),
                destination,
                self.tool(name),
                self.emitted,
            )
        self.assertRaises(
            ArchiveError,
            archive.extract,
            self.path("text.vbp"),
            destination,
            Tool("bsdtar", self.path("no-such-tool")),
            self.emitted,
        )

    def big_file(self):
        # more than a pipe holds
        path = self.path("big.vbp")
        with open(path, "wb") as fp:
            fp.write(bytes(4 * MiB))
        return path

    def test_a_tool_that_stops_reading(self):
        tar = self.script("tar", 'echo "not an archive" >&2\nexit 2\n')
        destination = self.path("out")
        os.makedirs(destination)
        with self.assertRaises(ArchiveError) as cm:
            archive.extract(
                self.big_file(), destination, Tool("gnutar", tar), self.emitted
            )
        self.assertEqual(str(cm.exception), "tar: not an archive")

    def test_cancelling_stops_the_tool(self):
        pid_file = self.path("bin", "tar.pid")
        tar = self.script(
            "tar", f'echo $$ > "{pid_file}"\nexec cat > /dev/null\n'
        )
        destination = self.path("out")
        os.makedirs(destination)

        def cancel(obj):
            raise archive.ArchiveCancelled()

        self.assertRaises(
            archive.ArchiveCancelled,
            archive.extract,
            self.big_file(),
            destination,
            Tool("gnutar", tar),
            cancel,
        )
        self.assertStopped(pid_file)

    def test_tarfile_refuses_what_it_would_misread(self):
        path = self.lab()
        self.patch(archive, "is_misread_sparse", lambda info: True)
        self.assertRaises(
            archive.ToolNeeded,
            archive.extract,
            path,
            self.path(),
            Tool("tarfile"),
            self.emitted,
        )

    def test_sparsify(self):
        path = sparse_file(self.path("full"), 0)
        with open(path, "wb") as fp:
            fp.write(b"head" + bytes(4 * MiB) + b"tail")
        self.assertTrue(archive.sparsify(path))
        self.assertLess(os.stat(path).st_blocks * 512, MiB)
        with open(path, "rb") as fp:
            data = fp.read()
        self.assertEqual(data, b"head" + bytes(4 * MiB) + b"tail")
        # not worth it
        with open(path, "wb") as fp:
            fp.write(b"x" * 100)
        self.assertFalse(archive.sparsify(path))


class TestProcess(ArchiveTestCase):

    def main(self, job):
        stdin = io.StringIO(dumps_toml(job))
        stdout = io.StringIO()
        self.patch(signal, "signal", lambda *args: None)
        self.patch(os, "nice", lambda n: 0)
        code = archive.main(stdin, stdout)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        return code, lines

    def test_inspect(self):
        path = make_archive(self.path("lab.vbp"), {"project.toml": PROJECT})
        code, lines = self.main({"job": "inspect", "archive": path})
        self.assertEqual(code, 0)
        result = ArchiveContents.from_table(lines[-1]["result"])
        self.assertEqual(result.path, path)

    def test_errors(self):
        code, lines = self.main({"job": "inspect", "archive": "/gone"})
        self.assertEqual(code, 2)
        self.assertIn("/gone", lines[-1]["error"])
        code, lines = self.main({"job": "dance"})
        self.assertEqual(
            (code, lines[-1]), (2, {"error": "unknown job 'dance'"})
        )

    def test_a_bug(self):
        def run_job(job, emit):
            raise ZeroDivisionError()

        self.patch(archive, "run_job", run_job)
        code, lines = self.main({"job": "inspect"})
        self.assertEqual(code, 3)
        self.assertIn("ZeroDivisionError", lines[-1]["error"])

    def test_cancelled(self):
        def run_job(job, emit):
            archive._on_sigterm(signal.SIGTERM, None)

        self.patch(archive, "run_job", run_job)
        self.assertEqual(self.main({"job": "inspect"}), (1, []))

    def test_nice_may_fail(self):
        def nice(n):
            raise OSError("not permitted")

        stdin = io.StringIO(dumps_toml({"job": "dance"}))
        self.patch(signal, "signal", lambda *args: None)
        self.patch(os, "nice", nice)
        self.assertEqual(archive.main(stdin, io.StringIO()), 2)


class FakeTransport:
    def __init__(self):
        self.written = b""
        self.closed = False
        self.signals = []

    def write(self, data):
        self.written += data

    def closeStdin(self):
        self.closed = True

    def signalProcess(self, name):
        self.signals.append(name)


class TestArchiveJob(ArchiveTestCase):

    def job(self, **kwargs):
        job = ArchiveJob({"job": "inspect", "archive": "/a.vbp"}, **kwargs)
        self.transport = FakeTransport()
        job.protocol.makeConnection(self.transport)
        return job

    def end(self, job, code=0):
        reason = (
            error.ProcessDone(0)
            if code == 0
            else error.ProcessTerminated(code)
        )
        job.protocol.processEnded(failure.Failure(reason))

    def test_the_job_on_stdin(self):
        self.job()
        self.assertTrue(self.transport.closed)
        self.assertIn(b'job = "inspect"', self.transport.written)

    def test_messages(self):
        progress, heads = [], []
        job = self.job(
            on_progress=lambda *args: progress.append(args),
            on_head=heads.append,
        )
        job.protocol.outReceived(b'{"progress": {"step": "read", "done": 1,')
        job.protocol.outReceived(b' "total": 2}}\n{"head": {"x": 1}}\n\n')
        job.protocol.outReceived(
            b'not json\n[1]\n{"other": 1}\n{"result": 42}\n'
        )
        self.assertEqual(progress, [("read", 1, 2)])
        self.assertEqual(heads, [{"x": 1}])
        self.assertNoResult(job.done)
        self.end(job)
        self.assertEqual(self.successResultOf(job.done), 42)

    def test_messages_without_listeners(self):
        job = self.job()
        job.protocol.outReceived(
            b'{"progress": {"step": "read", "done": 1, "total": 2}}\n'
            b'{"head": {}}\n{"result": null}\n'
        )
        self.end(job)
        self.assertIsNone(self.successResultOf(job.done))

    def test_error(self):
        job = self.job()
        job.protocol.outReceived(b'{"error": "disk full"}\n')
        self.end(job, 2)
        self.assertEqual(
            str(self.failureResultOf(job.done, ArchiveError).value),
            "disk full",
        )

    def test_the_process_dies(self):
        leftover = self.path("staging")
        os.makedirs(os.path.join(leftover, "sub"))
        job = self.job()
        job.leftovers.append(leftover)
        os.makedirs(self.path("shared_images"))
        created = sparse_file(self.path("shared_images", "deb"), 0)
        job.protocol.outReceived(
            json.dumps({"created": created}).encode() + b"\n"
        )
        job.protocol.outReceived(
            json.dumps({"created": self.path("gone")}).encode() + b"\n"
        )
        job.protocol.errReceived(b"Traceback: killed\n")
        self.end(job, 9)
        self.assertIn(
            "killed", str(self.failureResultOf(job.done, ArchiveError).value)
        )
        self.assertFalse(os.path.exists(leftover))
        self.assertFalse(os.path.exists(created))

    def test_no_message_at_all(self):
        job = self.job()
        self.end(job, 1)
        self.assertEqual(
            str(self.failureResultOf(job.done, ArchiveError).value),
            "the process stopped",
        )

    def test_cancel(self):
        job = self.job()
        job.cancel()
        self.assertEqual(self.transport.signals, ["TERM"])
        self.end(job, 1)
        self.failureResultOf(job.done, archive.ArchiveCancelled)
        # after the end there's nothing to stop
        job.cancel()
        self.assertEqual(self.transport.signals, ["TERM"])

    def test_signal_errors_are_ignored(self):
        job = self.job()

        def signalProcess(name):
            raise error.ProcessExitedAlready()

        self.transport.signalProcess = signalProcess
        job.cancel()

    def test_start(self):
        spawned = []

        class Reactor:
            def spawnProcess(self, protocol, executable, args, env):
                spawned.append((protocol, executable, args))

        job = ArchiveJob({"job": "inspect"})
        self.assertIs(job.start(Reactor()), job)
        [(protocol, executable, args)] = spawned
        self.assertIs(protocol, job.protocol)
        self.assertEqual(args[1:], ["-m", "virtualbricks.config.archive"])


class TestTheRealProcess(ArchiveTestCase):
    """One job through a real process, as the application runs it."""

    def test_inspect_archive(self):
        path = make_archive(
            self.path("lab.vbp"),
            {"project.toml": PROJECT, "README": b"A lab", "vm_hda.cow": b"x"},
        )
        heads = []
        job = archive.inspect_archive(path, on_head=heads.append)

        def check(contents):
            self.assertIsInstance(contents, ArchiveContents)
            self.assertEqual(contents.description, "A lab")
            self.assertEqual(len(heads), 1)
            self.assertFalse(heads[0].complete)

        return job.done.addCallback(check)

    def test_inspect_without_listeners(self):
        path = make_archive(self.path("lab.vbp"), {"project.toml": PROJECT})
        job = archive.inspect_archive(path)
        return job.done.addCallback(
            lambda contents: self.assertTrue(contents.complete)
        )

    def test_a_failure(self):
        job = archive.inspect_archive(self.path("gone.vbp"))
        d = self.assertFailure(job.done, ArchiveError)
        return d.addCallback(lambda exc: self.assertIn("gone.vbp", str(exc)))

    def test_subprocess_is_there(self):
        # the process needs nothing the test environment lacks
        result = subprocess.run(
            [sys.executable, "-c", "import virtualbricks.config"],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class TestWrite(ArchiveTestCase):

    def lab(self):
        project = self.path("lab")
        os.makedirs(os.path.join(project, "sub"), exist_ok=True)
        for name, data in (
            ("project.toml", PROJECT),
            ("README", b"A lab"),
            ("notes.txt", b"x" * 300),
            ("sub/small", b"y"),
        ):
            with open(os.path.join(project, name), "wb") as fp:
                fp.write(data)
        sparse_file(os.path.join(project, "vm_hda.cow"), 32 * MiB)
        sparse_file(os.path.join(project, "vm_hdb.cow"), 8 * MiB)
        image = sparse_file(self.path("deb.qcow2"), 64 * MiB, b"image")
        files = [
            "vm_hda.cow",
            "notes.txt",
            "project.toml",
            "sub/small",
            "vm_hdb.cow",
            "README",
        ]
        return project, files, [("deb", image)]

    def export(self, tool, output=None, qemu_img="", emit=None):
        project, files, images = self.lab()
        output = output or self.path("out.vbp")
        job = {
            "job": "export",
            "project": project,
            "output": output,
            "files": files,
            "images": [list(image) for image in images],
            "qemu_img": qemu_img,
        }
        return archive.run_job(job, emit or self.emitted, tool), output

    def test_the_order_of_a_new_archive(self):
        project, files, images = self.lab()
        names = [
            n for n, _, _ in archive.order_members(project, files, images)
        ]
        self.assertEqual(
            names,
            [
                "project.toml",
                "README",
                "sub/small",
                "notes.txt",
                "vm_hdb.cow",
                "vm_hda.cow",
                ".images/deb",
            ],
        )

    def check(self, output):
        # contents.toml first, then the small files
        with tarfile.open(output) as tar:
            names = [archive.normalize(info.name) for info in tar.getmembers()]
        self.assertEqual(names[0], "contents.toml")
        self.assertEqual(names[-1], ".images/deb")
        contents = archive.inspect(output, Tool("tarfile"), Emitted())
        self.assertEqual(
            [m.name for m in contents.members][:2], ["project.toml", "README"]
        )
        self.assertEqual(contents.description, "A lab")
        # every reader gets the holes back
        for reader in ("bsdtar", "tarfile"):
            destination = self.path(
                f"back-{reader}-{os.path.basename(output)}"
            )
            os.makedirs(destination)
            archive.extract(output, destination, self.tool(reader), Emitted())
            disk = os.path.join(destination, "vm_hda.cow")
            self.assertEqual(os.path.getsize(disk), 32 * MiB)
            self.assertLess(os.stat(disk).st_blocks * 512, MiB)
            with open(os.path.join(destination, ".images", "deb"), "rb") as fp:
                self.assertEqual(fp.read(5), b"image")
            with open(os.path.join(destination, "sub", "small"), "rb") as fp:
                self.assertEqual(fp.read(), b"y")

    def test_write_with_every_tool(self):
        for name in ("bsdtar", "gnutar", "tarfile"):
            output = self.path(f"out-{name}.vbp")
            result, output = self.export(self.tool(name), output)
            self.assertEqual(result["output"], output)
            self.assertEqual(result["size"], os.path.getsize(output))
            self.check(output)
            shutil.rmtree(self.path("lab"))

    def test_progress_and_what_was_created(self):
        result, output = self.export(Tool("tarfile"))
        progress = self.emitted.of("progress")[-1]
        self.assertEqual(progress["step"], "write")
        self.assertEqual(progress["done"], progress["total"])
        # the data, without the holes
        self.assertLess(progress["total"], MiB)
        part, staging = self.emitted.of("created")
        self.assertTrue(part.endswith(".part"))
        # next to the archive, as the packed disks can be large
        for path in (part, staging):
            self.assertFalse(os.path.exists(path))
            self.assertEqual(os.path.dirname(path), self.root)

    def test_a_failure_leaves_nothing(self):
        with self.assertRaises(ArchiveError):
            self.export(Tool("bsdtar", self.path("no-such-tool")))
        with self.assertRaises(ArchiveError):
            self.export(Tool("bsdtar", "/bin/false"))
        self.assertEqual(sorted(os.listdir(self.root)), ["deb.qcow2", "lab"])

    def test_cancelling_stops_the_tool(self):
        pid_file = self.path("bin", "tar.pid")
        tar = self.script(
            "tar", f'echo $$ > "{pid_file}"\nexec cat /dev/zero\n'
        )

        def cancel(obj):
            if "progress" in obj:
                raise archive.ArchiveCancelled()

        with self.assertRaises(archive.ArchiveCancelled):
            self.export(Tool("bsdtar", tar), emit=cancel)
        self.assertStopped(pid_file)
        self.assertEqual(
            sorted(os.listdir(self.root)), ["bin", "deb.qcow2", "lab"]
        )

    def test_disks_that_qemu_img_cannot_read_go_as_they_are(self):
        qemu_img = self.script(
            "qemu-img", 'echo "Could not open" >&2\nexit 1\n'
        )
        result, output = self.export(Tool("tarfile"), qemu_img=qemu_img)
        report = archive.report_from_list(result["report"])
        self.assertEqual(
            sorted(m.where for m in report),
            [".images/deb", "vm_hda.cow", "vm_hdb.cow"],
        )
        self.assertEqual(
            {m.text for m in report},
            {"stored as it is: qemu-img: Could not open"},
        )
        contents = archive.inspect(output, Tool("tarfile"), lambda obj: None)
        self.assertFalse(any(m.packed for m in contents.members))

    def test_a_failed_packing_leaves_no_partial_copy(self):
        # qemu-img writes part of the copy, then fails
        qemu_img = self.script(
            "qemu-img",
            """case "$1" in
    info) echo '{"format": "qcow2"}' ;;
    convert)
        for last; do :; done
        echo partial > "$last"
        echo "No space left" >&2
        exit 1 ;;
esac
""",
        )
        result, output = self.export(Tool("tarfile"), qemu_img=qemu_img)
        report = archive.report_from_list(result["report"])
        self.assertEqual(
            {m.text for m in report},
            {"stored as it is: qemu-img: No space left"},
        )
        with tarfile.open(output) as tar:
            self.assertEqual(tar.extractfile(".images/deb").read(5), b"image")
            self.assertEqual(tar.extractfile("vm_hda.cow").read(5), b"data\0")

    def test_uncompressed(self):
        project, files, images = self.lab()
        job = {
            "job": "export",
            "project": project,
            "output": self.path("plain.vbp"),
            "files": files,
            "compression": "none",
        }
        archive.run_job(job, self.emitted, Tool("tarfile"))
        self.assertEqual(archive.compression_flags(self.path("plain.vbp")), [])

    def test_stored_size(self):
        path = sparse_file(self.path("sparse"), 16 * MiB, b"x" * 10)
        self.assertLess(archive.stored_size(path), MiB)
        with open(self.path("full"), "wb") as fp:
            fp.write(b"x" * 100)
        self.assertEqual(archive.stored_size(self.path("full")), 100)

    def test_large_sizes_in_the_header(self):
        info = archive._SparseInfo("GNUSparseFile.0/big")
        info.size = 12 << 30
        info.pax_headers = {"GNU.sparse.major": "1"}
        buf = info.tobuf(tarfile.PAX_FORMAT)
        header = buf[-tarfile.BLOCKSIZE :]
        # base-256, not a PAX record
        self.assertEqual(header[124] & 0x80, 0x80)
        self.assertNotIn(b" size=", buf)
        self.assertEqual(tarfile.nti(header[124:136]), 12 << 30)
        small = archive._SparseInfo("small")
        small.size = 10
        self.assertEqual(
            small.tobuf(tarfile.PAX_FORMAT),
            tarfile.TarInfo.tobuf(small, tarfile.PAX_FORMAT),
        )

    def test_sparse_data(self):
        path = sparse_file(self.path("f"), 4 * MiB, b"abc")
        fd = os.open(path, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        data = archive._SparseData(fd, [(0, 3), (4 * MiB, 0)])
        self.assertTrue(data.head.startswith(b"2\n0\n3\n4194304\n0\n"))
        self.assertEqual(len(data.head) % tarfile.BLOCKSIZE, 0)
        self.assertEqual(data.read(), data.head + b"abc")
        shrunk = archive._SparseData(fd, [(8 * MiB, 10)])
        shrunk.read(len(shrunk.head))
        self.assertRaises(OSError, shrunk.read)

    def test_export_project(self):
        spawned = []

        class Reactor:
            def spawnProcess(self, protocol, executable, args, env):
                spawned.append(protocol)

        job = archive.export_project(
            "/labs/lab",
            "/out.vbp",
            ["project.toml"],
            [("deb", "/d")],
            reactor=Reactor(),
        )
        self.assertEqual(spawned, [job.protocol])
        self.assertEqual(job.job["job"], "export")
        self.assertEqual(job.job["images"], [["deb", "/d"]])
        self.assertEqual(job.job["compression"], "gzip")


class TestExportInTheRealProcess(ArchiveTestCase):
    """One export through a real process."""

    lab = TestWrite.lab
    check = TestWrite.check

    def test_the_process(self):
        project, files, images = self.lab()
        output = self.path("real.vbp")
        job = archive.export_project(project, output, files, images)

        def check(result):
            self.assertEqual(result["output"], output)
            self.check(output)

        return job.done.addCallback(check)


# qemu-img that logs its arguments, says it's half done, then done, and
# writes its last argument when it converts; it fails when asked to.
FAKE_QEMU_IMG = """echo "$@" >> "{log}"
printf '    (50.00/100%%)\\r'
if [ "$1" = convert ]; then
    for last; do :; done
    echo image > "$last"
fi
[ -e "{fail}" ] && {{ echo "No space left on device" >&2; exit 1; }}
printf '    (100.00/100%%)\\r'
exit 0
"""


class ImageJobTestCase(ArchiveTestCase):
    """The fake qemu-img, and the shared images."""

    def setUp(self):
        super().setUp()
        self.log = self.path("qemu-img.log")
        self.failing = self.path("qemu-img.fail")
        self.qemu_img = self.script(
            "qemu-img", FAKE_QEMU_IMG.format(log=self.log, fail=self.failing)
        )
        self.output = self.path("shared_images", "frr-r1.qcow2")
        os.makedirs(os.path.dirname(self.output))


class TestImageJobs(ImageJobTestCase):

    def calls(self):
        with open(self.log) as fp:
            return [line.split() for line in fp.read().splitlines()]

    def save(self):
        return archive.run_job(
            {
                "job": "write-image",
                "disk": "/lab/r1_hda.cow",
                "output": self.output,
                "qemu_img": self.qemu_img,
            },
            self.emitted,
        )

    def test_save(self):
        result = self.save()
        self.assertEqual(result["output"], self.output)
        self.assertEqual(result["size"], archive.stored_size(self.output))
        self.assertEqual(
            self.calls(),
            [
                [
                    "convert",
                    "-p",
                    "-O",
                    "qcow2",
                    "-m",
                    "8",
                    "-W",
                    "/lab/r1_hda.cow",
                    self.output,
                ]
            ],
        )
        # a stopped job leaves no file
        self.assertEqual(self.emitted.of("created"), [self.output])
        progress = self.emitted.of("progress")
        self.assertEqual(
            progress[-1], {"step": "save", "done": 100, "total": 100}
        )

    def test_save_fails(self):
        open(self.failing, "w").close()
        with self.assertRaises(ArchiveError) as cm:
            self.save()
        self.assertIn("No space left", str(cm.exception))
        self.assertFalse(os.path.lexists(self.output))

    def test_a_file_there_already(self):
        with open(self.output, "w") as fp:
            fp.write("mine")
        self.assertRaises(ArchiveError, self.save)
        self.assertEqual(self.emitted.of("created"), [])
        with open(self.output) as fp:
            self.assertEqual(fp.read(), "mine")

    def test_without_qemu_img(self):
        with self.assertRaises(ArchiveError) as cm:
            archive.run_job(
                {"job": "commit-image", "disk": "/lab/r1_hda.cow"},
                self.emitted,
            )
        self.assertEqual(str(cm.exception), "qemu-img is needed")

    def test_merge(self):
        result = archive.run_job(
            {
                "job": "commit-image",
                "disk": "/lab/r1_hda.cow",
                "qemu_img": self.qemu_img,
            },
            self.emitted,
        )
        self.assertEqual(result, {"disk": "/lab/r1_hda.cow"})
        self.assertEqual(self.calls(), [["commit", "-p", "/lab/r1_hda.cow"]])
        steps = self.emitted.of("progress")
        self.assertEqual({p["step"] for p in steps}, {"merge"})
        self.assertEqual(steps[-1]["done"], 100)

    def test_from_the_application(self):
        spawned = []

        class Reactor:
            def spawnProcess(self, protocol, executable, args, env):
                spawned.append(protocol)

        self.patch(archive, "find_qemu_img", lambda: "/usr/bin/qemu-img")
        progress = []
        job = archive.save_image(
            "/lab/r1_hda.cow",
            self.output,
            lambda *args: progress.append(args),
            reactor=Reactor(),
        )
        self.assertEqual(
            job.job,
            {
                "job": "write-image",
                "disk": "/lab/r1_hda.cow",
                "output": self.output,
                "qemu_img": "/usr/bin/qemu-img",
            },
        )
        job = archive.merge_image(
            "/lab/r1_hda.cow", qemu_img=self.qemu_img, reactor=Reactor()
        )
        self.assertEqual(
            job.job,
            {
                "job": "commit-image",
                "disk": "/lab/r1_hda.cow",
                "qemu_img": self.qemu_img,
            },
        )
        self.assertEqual(len(spawned), 2)


class TestImageJobInTheRealProcess(ImageJobTestCase):
    """A save through a real process, with the fake qemu-img."""

    def test_the_process(self):
        progress = []
        job = archive.save_image(
            "/lab/r1_hda.cow",
            self.output,
            lambda *args: progress.append(args),
            qemu_img=self.qemu_img,
        )

        def check(result):
            self.assertEqual(result["output"], self.output)
            self.assertEqual(progress[-1], ("save", 100, 100))

        return job.done.addCallback(check)

    def test_a_failure_leaves_no_file(self):
        open(self.failing, "w").close()
        job = archive.save_image(
            "/lab/r1_hda.cow", self.output, qemu_img=self.qemu_img
        )

        def check(failure):
            failure.trap(ArchiveError)
            self.assertFalse(os.path.lexists(self.output))

        return job.done.addCallbacks(
            lambda result: self.fail(f"it should have failed: {result}"),
            check,
        )
