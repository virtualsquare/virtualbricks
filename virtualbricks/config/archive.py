# -*- test-case-name: virtualbricks.tests.config.test_archive -*-
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
Archives of projects, read and written in a process of their own.

An archive can hold gigabytes of disk images, so the work on it runs in a
process of its own, which runs ``main()``, never in the application. The
application writes the job to the process's stdin, as TOML, and reads one JSON
object a line from its stdout:

- ``{"progress": {"step": ..., "done": ..., "total": ...}}``, in bytes;
- ``{"head": {...}}``: what an inspection knows before the end of the
  archive;
- ``{"created": path}``: a file outside the job's folder, removed if the job
  doesn't finish;
- ``{"result": ...}`` or ``{"error": message}``, last.

SIGTERM cancels the job: the process removes what it wrote and exits with 1.

The archive tool is ``bsdtar`` when it's installed, otherwise GNU tar,
otherwise Python's ``tarfile``. The head of an archive, the small files at its
start, is always read with ``tarfile``, whatever the compression.

A new archive starts with ``contents.toml``, the list of its members, then the
project file and the README, and ends with the disks, the largest last. An
archive without the list, as every older one, has to be read to its end to
know what it holds.
"""

from __future__ import annotations

import dataclasses
import json
import os
import posixpath
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from collections.abc import Callable, Iterable
from typing import IO, TYPE_CHECKING, Any

from twisted.internet import defer, protocol

from virtualbricks import locations
from virtualbricks.config import projectfile, tomlfile
from virtualbricks.config.projectfile import ProjectFormatError
from virtualbricks.config.report import Message, Report

if TYPE_CHECKING:
    from virtualbricks.config.tomlfile import Table

# The format of contents.toml.
FORMAT = 1
CONTENTS = "contents.toml"
README = "README"
IMAGES = ".images"
# The largest size the octal field of a tar header holds.
OCTAL_SIZE_MAX = 8**11 - 1
CHUNK = 1 << 20
# Private disks, "<vm>_<device>.cow", at the top of the project.
PRIVATE_DISK = re.compile(r"[^/]+_[a-z0-9]+\.cow\Z")

# The kinds of members.
PROJECT = "project"
LEGACY_PROJECT = "legacy project"
CONTENTS_KIND = "contents"
README_KIND = "readme"
IMAGE = "image"
DISK = "disk"
OTHER = "other"
HEAD = frozenset((CONTENTS_KIND, PROJECT, LEGACY_PROJECT, README_KIND))


class ArchiveError(Exception):
    """The archive can't be read or written."""


class Cancelled(Exception):
    """The application asked the job to stop."""


class ToolNeeded(ArchiveError):
    """tarfile would read the archive wrong, and no other tool is installed."""


# The archive tool

BSDTAR = "bsdtar"
GNUTAR = "gnutar"
TARFILE = "tarfile"


@dataclasses.dataclass(frozen=True)
class Tool:
    name: str
    path: str = ""


def find_tool(
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., Any] = subprocess.run,
) -> Tool:
    """bsdtar, otherwise GNU tar, otherwise tarfile."""

    path = which("bsdtar")
    if path:
        return Tool(BSDTAR, path)
    path = which("tar")
    if path:
        try:
            result = run(
                [path, "--version"], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            pass
        else:
            # BusyBox's tar doesn't handle holes.
            if "GNU tar" in result.stdout.split("\n", 1)[0]:
                return Tool(GNUTAR, path)
    return Tool(TARFILE)


# Members


def normalize(name: str) -> str:
    """The name of a member without a leading "./" or a trailing "/"."""

    while name.startswith("./"):
        name = name[2:]
    return name.rstrip("/")


def member_kind(name: str) -> str:
    name = normalize(name)
    if name == CONTENTS:
        return CONTENTS_KIND
    if name == locations.PROJECT_FILE:
        return PROJECT
    if name in (
        locations.LEGACY_PROJECT_FILE,
        locations.LEGACY_PROJECT_FILE + "~",
    ):
        return LEGACY_PROJECT
    if name == README:
        return README_KIND
    if name.startswith(IMAGES + "/") and name.count("/") == 1:
        return IMAGE
    if PRIVATE_DISK.match(name):
        return DISK
    return OTHER


@dataclasses.dataclass(frozen=True)
class Member:
    name: str
    size: int
    kind: str

    @property
    def image(self) -> str:
        """The name of the image, for a member of .images/."""

        return posixpath.basename(self.name)


@dataclasses.dataclass
class ArchiveContents:
    """What an inspection found in an archive."""

    path: str
    # The project file, converted if it's old.
    data: Table
    description: str
    members: list[Member]
    # Whether members lists every member of the archive.
    complete: bool
    report: Report = dataclasses.field(default_factory=Report)
    # Whether the project file was converted from an older Virtualbricks.
    converted: bool = False

    @property
    def images(self) -> dict[str, Member]:
        return {m.image: m for m in self.members if m.kind == IMAGE}

    @property
    def size(self) -> int:
        return sum(m.size for m in self.members)

    def to_table(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "data": self.data,
            "description": self.description,
            "members": [[m.name, m.size, m.kind] for m in self.members],
            "complete": self.complete,
            "report": report_to_list(self.report),
            "converted": self.converted,
        }

    @classmethod
    def from_table(cls, table: dict[str, Any]) -> ArchiveContents:
        return cls(
            table["path"],
            table["data"],
            table["description"],
            [Member(*m) for m in table["members"]],
            table["complete"],
            report_from_list(table["report"]),
            table["converted"],
        )


def report_to_list(report: Report) -> list[list[str]]:
    return [[m.level, m.text, m.where] for m in report]


def report_from_list(items: Iterable[list[str]]) -> Report:
    report = Report()
    report.messages.extend(Message(*item) for item in items)
    return report


# Reading


class Progress:
    """Send the progress of a step, at most ten times a second."""

    def __init__(self, emit, step: str, total: int, clock=time.monotonic):
        self.emit = emit
        self.step = step
        self.total = total
        self.done = 0
        self.clock = clock
        self._last = -1.0

    def advance(self, count: int) -> None:
        self.done += count
        now = self.clock()
        if now - self._last >= 0.1:
            self._last = now
            self.send()

    def send(self) -> None:
        self.emit(
            {
                "progress": {
                    "step": self.step,
                    "done": self.done,
                    "total": self.total,
                }
            }
        )


class CountingReader:
    """A file that tells progress how much of it was read."""

    def __init__(self, fp: IO[bytes], progress: Progress) -> None:
        self.fp = fp
        self.progress = progress

    def read(self, size: int = -1) -> bytes:
        data = self.fp.read(size)
        self.progress.advance(len(data))
        return data


def is_misread_sparse(tarinfo: tarfile.TarInfo) -> bool:
    """
    Whether tarfile reads this member wrong.

    A GNU sparse 1.0 member whose size is in a PAX record, as bsdtar and GNU
    tar write it for more than 8 GiB, gets the wrong size in Python 3.10 to
    3.13, and the member after it is lost.
    """

    pax = tarinfo.pax_headers
    return pax.get("GNU.sparse.major") == "1" and "size" in pax


def _check(tarinfo: tarfile.TarInfo, tool: Tool) -> None:
    if is_misread_sparse(tarinfo):
        if tool.name == TARFILE:
            raise ToolNeeded(
                f"{tarinfo.name}: install bsdtar or GNU tar to read this"
                " archive"
            )
        raise _UseTool()


class _UseTool(Exception):
    """Read the archive with the tool: tarfile would read it wrong."""


class _Head:
    """The small files at the start of an archive, as they are read."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.members: list[Member] = []
        self.listed: list[Member] | None = None

    def add(self, member: Member, data: bytes | None) -> None:
        self.members.append(member)
        if data is not None:
            self.files[member.kind] = data
            if member.kind == CONTENTS_KIND:
                self.listed = read_contents(data)

    def has_project(self) -> bool:
        return PROJECT in self.files or LEGACY_PROJECT in self.files

    def is_read(self) -> bool:
        """Whether the list says there's nothing more in the head."""

        if self.listed is None:
            return False
        wanted = {m.kind for m in self.listed if m.kind in HEAD}
        return wanted <= set(self.files)


def read_contents(data: bytes) -> list[Member]:
    try:
        table = tomlfile.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomlfile.DecodeError) as exc:
        raise ArchiveError(f"{CONTENTS}: {exc}") from None
    if table.get("format") != FORMAT:
        raise ArchiveError(
            f"{CONTENTS}: written by a newer Virtualbricks"
            f" (format {table.get('format')!r})"
        )
    members = []
    for item in table.get("members", []):
        if isinstance(item, dict):
            name = str(item.get("name", ""))
            size = item.get("size", 0)
            members.append(
                Member(
                    name,
                    size if isinstance(size, int) else 0,
                    member_kind(name),
                )
            )
    return members


def write_contents(members: Iterable[Member]) -> str:
    table: Table = {
        "format": FORMAT,
        "members": [{"name": m.name, "size": m.size} for m in members],
    }
    return tomlfile.dumps(table)


def contents_from_head(
    path: str, head: _Head, complete: bool
) -> ArchiveContents:
    """Read the project file and the README of the head."""

    report = Report()
    converted = False
    if PROJECT in head.files:
        try:
            data = tomlfile.loads(head.files[PROJECT].decode("utf-8"))
        except (UnicodeDecodeError, tomlfile.DecodeError) as exc:
            raise ArchiveError(f"{locations.PROJECT_FILE}: {exc}") from None
        try:
            data = projectfile.upgrade(data, report)
        except ProjectFormatError as exc:
            raise ArchiveError(f"{locations.PROJECT_FILE}: {exc}") from None
    elif LEGACY_PROJECT in head.files:
        data = convert_legacy(head.files[LEGACY_PROJECT], report)
        converted = True
    else:
        raise ArchiveError("the archive has no project file")
    description = head.files.get(README_KIND, b"").decode("utf-8", "replace")
    members = head.listed if head.listed is not None else head.members
    return ArchiveContents(
        path, data, description, list(members), complete, report, converted
    )


def convert_legacy(text: bytes, report: Report) -> Table:
    """Convert the project file of an older Virtualbricks, in memory."""

    # Imported here: the migration imports config, not the other way.
    from virtualbricks.migrate import convert_imported_project

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, locations.LEGACY_PROJECT_FILE)
        with open(path, "wb") as fp:
            fp.write(text)
        data = convert_imported_project(directory, report)
    if data is None:
        raise ArchiveError(
            "the project file can't be converted: "
            + "; ".join(str(m) for m in report if m.level == "error")
        )
    return data


def inspect(path: str, tool: Tool, emit) -> ArchiveContents:
    """
    Read what an archive holds.

    A new archive is read up to the end of its head. Of an archive without
    contents.toml, the head is sent as soon as the project file is read,
    then the rest is read for the list of members.
    """

    try:
        return _inspect_with_tarfile(path, tool, emit)
    except _UseTool:
        return _inspect_with_tool(path, tool, emit)


def _inspect_with_tarfile(path: str, tool: Tool, emit) -> ArchiveContents:
    head = _Head()
    sent = False
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fp:
            progress = Progress(emit, "read", size)
            reader = CountingReader(fp, progress)
            with tarfile.open(fileobj=reader, mode="r|*") as tar:
                for tarinfo in tar:
                    _check(tarinfo, tool)
                    if not tarinfo.isfile():
                        continue
                    member = Member(
                        normalize(tarinfo.name),
                        tarinfo.size,
                        member_kind(tarinfo.name),
                    )
                    data = None
                    if member.kind in HEAD:
                        data = tar.extractfile(tarinfo).read()
                    head.add(member, data)
                    if head.is_read():
                        return contents_from_head(path, head, True)
                    if head.listed is None and head.has_project() and not sent:
                        contents = contents_from_head(path, head, False)
                        emit({"head": contents.to_table()})
                        sent = True
            progress.send()
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise ArchiveError(f"{path}: {exc}") from None
    return contents_from_head(path, head, True)


def _inspect_with_tool(path: str, tool: Tool, emit) -> ArchiveContents:
    head = _Head()
    for member in list_with_tool(tool, path):
        data = None
        if member.kind in HEAD:
            data = read_with_tool(tool, path, member.name)
        head.add(member, data)
    return contents_from_head(path, head, True)


def _run_tool(args: list[str]) -> bytes:
    try:
        result = subprocess.run(args, capture_output=True)
    except OSError as exc:
        raise ArchiveError(f"{args[0]}: {exc}") from None
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise ArchiveError(f"{args[0]}: {stderr}")
    return result.stdout


def list_with_tool(tool: Tool, path: str) -> list[Member]:
    if tool.name == BSDTAR:
        output = _run_tool([tool.path, "-t", "-v", "-f", path])
        return parse_listing(output.decode("utf-8", "replace"), 8)
    output = _run_tool(
        [tool.path, "-t", "-v", "--quoting-style=literal", "-f", path]
    )
    return parse_listing(output.decode("utf-8", "replace"), 5)


def parse_listing(text: str, fields: int) -> list[Member]:
    """
    The regular files of a verbose listing, of bsdtar or GNU tar.

    bsdtar writes eight fields before the name, as ls -l: permissions, links,
    owner, group, size, month, day, time or year. GNU tar writes five:
    permissions, owner/group, size, date, time.
    """

    size_field = 4 if fields == 8 else 2
    members = []
    for line in text.splitlines():
        parts = line.split(None, fields)
        if len(parts) <= fields or not parts[0].startswith("-"):
            continue
        name = normalize(parts[fields])
        try:
            size = int(parts[size_field])
        except ValueError:
            continue
        members.append(Member(name, size, member_kind(name)))
    return members


def read_with_tool(tool: Tool, path: str, name: str) -> bytes:
    return _run_tool([tool.path, "-x", "-O", "-f", path, name])


# Extracting


def _safe_member(tarinfo: tarfile.TarInfo, destination: str):
    """tarfile's data filter, or the same checks where Python lacks it."""

    data_filter = getattr(tarfile, "data_filter", None)
    if data_filter is not None:
        try:
            return data_filter(tarinfo, destination)
        except tarfile.FilterError:
            return None
    name = tarinfo.name
    if (
        os.path.isabs(name)
        or ".." in name.split("/")
        or tarinfo.islnk()
        or tarinfo.issym()
        or tarinfo.isdev()
    ):
        return None
    return tarinfo


# The first bytes of the compressed files, and GNU tar's option for them.
MAGIC = (
    (b"\x1f\x8b", "--gzip"),
    (b"BZh", "--bzip2"),
    (b"\xfd7zXZ\x00", "--xz"),
    (b"\x28\xb5\x2f\xfd", "--zstd"),
)


def compression_flags(path: str) -> list[str]:
    with open(path, "rb") as fp:
        start = fp.read(6)
    for magic, flag in MAGIC:
        if start.startswith(magic):
            return [flag]
    return []


def extract(path: str, destination: str, tool: Tool, emit) -> None:
    """
    Extract an archive into destination, keeping the holes of its files.

    The tools read the archive from a pipe, so the progress is the same with
    all three: the share of the archive read.
    """

    size = os.path.getsize(path)
    progress = Progress(emit, "extract", size)
    if tool.name == BSDTAR:
        args = [tool.path, "-x", "-S", "-f", "-", "-C", destination]
    elif tool.name == GNUTAR:
        args = [tool.path, "-x", "-f", "-", "-C", destination]
        # GNU tar doesn't recognize the compression of a pipe.
        args[2:2] = compression_flags(path)
    else:
        _extract_with_tarfile(path, destination, progress)
        progress.send()
        return
    _extract_with_tool(path, args, progress)
    progress.send()


def _extract_with_tool(path: str, args: list[str], progress: Progress):
    with tempfile.TemporaryFile() as stderr, open(path, "rb") as fp:
        try:
            process = subprocess.Popen(
                args, stdin=subprocess.PIPE, stderr=stderr
            )
        except OSError as exc:
            raise ArchiveError(f"{args[0]}: {exc}") from None
        try:
            try:
                while chunk := fp.read(CHUNK):
                    process.stdin.write(chunk)
                    progress.advance(len(chunk))
                process.stdin.close()
            except BrokenPipeError:
                pass
            code = process.wait()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        if code != 0:
            stderr.seek(0)
            text = stderr.read().decode("utf-8", "replace").strip()
            raise ArchiveError(f"{os.path.basename(args[0])}: {text}")


def _extract_with_tarfile(path: str, destination: str, progress: Progress):
    try:
        with open(path, "rb") as fp:
            reader = CountingReader(fp, progress)
            with tarfile.open(fileobj=reader, mode="r|*") as tar:
                for tarinfo in tar:
                    _check(tarinfo, Tool(TARFILE))
                    safe = _safe_member(tarinfo, destination)
                    if safe is not None:
                        tar.extract(safe, destination, set_attrs=False)
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise ArchiveError(f"{path}: {exc}") from None


def sparsify(path: str, block: int = 64 * 1024, least: int = CHUNK) -> bool:
    """
    Turn the runs of zeros of a file into holes, if they're worth it.

    GNU tar and tarfile write as zeros the holes an archive doesn't record.
    Return whether the file was rewritten.
    """

    zero = bytes(block)
    zeros = 0
    with open(path, "rb") as fp:
        while chunk := fp.read(block):
            if chunk == zero[: len(chunk)]:
                zeros += len(chunk)
    if zeros < least:
        return False
    size = os.path.getsize(path)
    tmp = path + ".sparse"
    with open(path, "rb") as fin, open(tmp, "wb") as fout:
        while chunk := fin.read(block):
            if chunk == zero[: len(chunk)]:
                fout.seek(len(chunk), os.SEEK_CUR)
            else:
                fout.write(chunk)
        fout.truncate(size)
    shutil.copystat(path, tmp)
    os.replace(tmp, path)
    return True


# The process


def _on_sigterm(signum, frame):
    raise Cancelled()


def run_job(job: Table, emit, tool: Tool | None = None) -> Any:
    """Run a job of the process and return its result."""

    if tool is None:
        tool = find_tool()
    kind = job.get("job")
    if kind == "inspect":
        return inspect(str(job["archive"]), tool, emit).to_table()
    if kind == "import":
        # Imported here: importing uses the reading above.
        from virtualbricks.config import importing

        return importing.run_import(job, emit, tool)
    raise ArchiveError(f"unknown job {kind!r}")


def main(stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout) -> int:
    def emit(obj: Any) -> None:
        stdout.write(json.dumps(obj) + "\n")
        stdout.flush()

    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        job = tomlfile.loads(stdin.read())
        emit({"result": run_job(job, emit)})
    except Cancelled:
        return 1
    except ArchiveError as exc:
        emit({"error": str(exc)})
        return 2
    except Exception:
        emit({"error": traceback.format_exc()})
        return 3
    return 0


# The application's side

# Not "-m virtualbricks.config.archive": the package imports this module, and
# runpy would warn that it runs a second copy of it.
PROCESS = (
    "import sys; from virtualbricks.config.archive import main; "
    "sys.exit(main())"
)


class ArchiveJob:
    """
    A job of the archive process, seen from the application.

    ``done`` fires with the result, or fails with ArchiveError; ``cancel()``
    stops the process. Files the process left behind, because it died
    without cleaning up, are removed: the job's folder and the files it said
    it created.
    """

    def __init__(
        self,
        job: Table,
        on_progress: Callable[[str, int, int], None] | None = None,
        on_head: Callable[[dict[str, Any]], None] | None = None,
        leftovers: Iterable[str] = (),
    ) -> None:
        self.job = job
        self.on_progress = on_progress
        self.on_head = on_head
        self.leftovers = list(leftovers)
        self.done = defer.Deferred()
        self.cancelled = False
        self.protocol = _ArchiveProtocol(self)
        self._result: Any = None
        self._has_result = False
        self._error: str | None = None

    def start(self, reactor=None) -> ArchiveJob:
        if reactor is None:
            from twisted.internet import reactor
        reactor.spawnProcess(
            self.protocol,
            sys.executable,
            [sys.executable, "-c", PROCESS],
            env=dict(os.environ),
        )
        return self

    def cancel(self) -> None:
        self.cancelled = True
        self.protocol.terminate()

    # From the protocol

    def connected(self, transport) -> None:
        transport.write(tomlfile.dumps(self.job).encode("utf-8"))
        transport.closeStdin()

    def message(self, obj: dict[str, Any]) -> None:
        if "progress" in obj:
            if self.on_progress is not None:
                p = obj["progress"]
                self.on_progress(p["step"], p["done"], p["total"])
        elif "head" in obj:
            if self.on_head is not None:
                self.on_head(obj["head"])
        elif "created" in obj:
            self.leftovers.append(obj["created"])
        elif "result" in obj:
            self._result = obj["result"]
            self._has_result = True
        elif "error" in obj:
            self._error = obj["error"]

    def ended(self, stderr: str) -> None:
        if self._has_result:
            self.done.callback(self._result)
            return
        for path in self.leftovers:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.lexists(path):
                os.remove(path)
        if self.cancelled:
            self.done.errback(Cancelled())
        else:
            error = self._error or stderr.strip() or "the process stopped"
            self.done.errback(ArchiveError(error))


class _ArchiveProtocol(protocol.ProcessProtocol):

    def __init__(self, job: ArchiveJob) -> None:
        self.job = job
        self._buffer = b""
        self._stderr = b""
        self._running = False

    def connectionMade(self) -> None:
        self._running = True
        self.job.connected(self.transport)

    def outReceived(self, data: bytes) -> None:
        self._buffer += data
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            if line.strip():
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    self.job.message(obj)

    def errReceived(self, data: bytes) -> None:
        self._stderr += data

    def terminate(self) -> None:
        if self._running:
            try:
                self.transport.signalProcess("TERM")
            except Exception:
                pass

    def processEnded(self, reason) -> None:
        self._running = False
        self.job.ended(self._stderr.decode("utf-8", "replace"))


def inspect_archive(
    path: str,
    on_head: Callable[[ArchiveContents], None] | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    reactor=None,
) -> ArchiveJob:
    """Read an archive in the process; done fires with ArchiveContents."""

    def head(table):
        if on_head is not None:
            on_head(ArchiveContents.from_table(table))

    job = ArchiveJob(
        {"job": "inspect", "archive": path}, on_progress, head
    ).start(reactor)
    job.done.addCallback(ArchiveContents.from_table)
    return job


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
