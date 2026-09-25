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

from virtualbricks.config import archive, dumps
from virtualbricks.config.archive import (
    ArchiveContents,
    ArchiveError,
    ArchiveJob,
    Member,
    Tool,
)
from virtualbricks.config.report import Report

MiB = 1 << 20
PROJECT = dumps(
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
        self.assertEqual(contents.data["bricks"]["sw"]["numports"], 8)

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
        stdin = io.StringIO(dumps(job))
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

        stdin = io.StringIO(dumps({"job": "dance"}))
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
        job.protocol.outReceived(b'not json\n[1]\n{"result": 42}\n')
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
        os.makedirs(self.path("vimages"))
        created = sparse_file(self.path("vimages", "deb"), 0)
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
        self.failureResultOf(job.done, archive.Cancelled)
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
        self.assertEqual(args[1:], ["-c", archive.PROCESS])


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
