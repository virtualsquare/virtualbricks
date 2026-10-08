# -*- test-case-name: virtualbricks.tests.config.test_archive -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

Two jobs work on disk images, as long as an archive: writing a disk with its
changes as a new image, with ``qemu-img convert``, and merging the changes
of a disk into its image, with ``qemu-img commit``.

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
import errno
import gzip
import io
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
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from types import FrameType
from typing import IO, Any, NoReturn, cast

from twisted.internet import defer, protocol
from twisted.internet.interfaces import IProcessTransport, IReactorProcess
from twisted.python.failure import Failure

from virtualbricks import locations
from virtualbricks.config.projectfile import (
    ProjectFormatError,
    upgrade_project,
)
from virtualbricks.config.report import Level, Message, Report
from virtualbricks.config.tomlfile import (
    DecodeError,
    Table,
    Value,
    dumps_toml,
    loads_toml,
)

# The format of contents.toml.
FORMAT = 1
CONTENTS = "contents.toml"
# The folder of the images; .images in the archives of Virtualbricks 2.1 and
# of the development versions of 3.0, which are still read.
IMAGES = "IMAGES"
LEGACY_IMAGES = ".images"
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

# What the process sends to the application: an object, a line of JSON.
Emit = Callable[[dict[str, Any]], None]
# What qemu-img says of an operation: its percent done.
OnPercent = Callable[[float], None]
# A member of a new archive: (arcname, path, kind).
Entry = tuple[str, str, str]


class ArchiveError(Exception):
    """The archive can't be read or written."""


class ArchiveCancelled(Exception):
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
    if name in (locations.README, locations.LEGACY_README):
        return README_KIND
    if name.split("/")[0] in (IMAGES, LEGACY_IMAGES) and name.count("/") == 1:
        return IMAGE
    if PRIVATE_DISK.match(name):
        return DISK
    return OTHER


@dataclasses.dataclass(frozen=True)
class Member:
    name: str
    # Its size in the archive.
    size: int
    kind: str
    # Whether it's a qcow2 disk that qemu-img compressed, and its size before.
    packed: bool = False
    real_size: int = 0

    @property
    def original_size(self) -> int:
        """Its size on the computer it comes from."""

        return self.real_size if self.packed else self.size

    @property
    def image(self) -> str:
        """The name of the image, for a member of IMAGES/."""

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
            "members": [
                [m.name, m.size, m.kind, m.packed, m.real_size]
                for m in self.members
            ],
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
    report.messages.extend(
        Message(cast("Level", level), text, where)
        for level, text, where in items
    )
    return report


# Reading


class Progress:
    """Send the progress of a step, at most ten times a second."""

    def __init__(
        self,
        emit: Emit,
        step: str,
        total: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
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
        # README.md is the README, if the archive has both
        if data is not None and not (
            normalize(member.name) == locations.LEGACY_README
            and README_KIND in self.files
        ):
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
        table = loads_toml(data.decode("utf-8"))
    except (UnicodeDecodeError, DecodeError) as exc:
        raise ArchiveError(f"{CONTENTS}: {exc}") from None
    if table.get("format") != FORMAT:
        raise ArchiveError(
            f"{CONTENTS}: written by a newer Virtualbricks"
            f" (format {table.get('format')!r})"
        )

    def number(value: object) -> int:
        return value if isinstance(value, int) else 0

    members = []
    items = table.get("members", [])
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            name = str(item.get("name", ""))
            members.append(
                Member(
                    name,
                    number(item.get("size", 0)),
                    member_kind(name),
                    item.get("packed") is True,
                    number(item.get("real_size", 0)),
                )
            )
    return members


def write_contents(members: Iterable[Member]) -> str:
    items: list[Value] = []
    for m in members:
        item: Table = {"name": m.name, "size": m.size}
        if m.packed:
            item["packed"] = True
            item["real_size"] = m.real_size
        items.append(item)
    return dumps_toml({"format": FORMAT, "members": items})


def contents_from_head(
    path: str, head: _Head, complete: bool
) -> ArchiveContents:
    """Read the project file and the README of the head."""

    report = Report()
    converted = False
    if PROJECT in head.files:
        try:
            data = loads_toml(head.files[PROJECT].decode("utf-8"))
        except (UnicodeDecodeError, DecodeError) as exc:
            raise ArchiveError(f"{locations.PROJECT_FILE}: {exc}") from None
        try:
            data = upgrade_project(data, report)
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


def inspect(path: str, tool: Tool, emit: Emit) -> ArchiveContents:
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


def _inspect_with_tarfile(
    path: str, tool: Tool, emit: Emit
) -> ArchiveContents:
    head = _Head()
    sent = False
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fp:
            progress = Progress(emit, "read", size)
            reader = CountingReader(fp, progress)
            # a stream: tarfile only reads it
            stream = cast("IO[bytes]", reader)
            with tarfile.open(fileobj=stream, mode="r|*") as tar:
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
                        # a regular file always has one
                        extracted = tar.extractfile(tarinfo)
                        data = extracted.read() if extracted else None
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


def _inspect_with_tool(path: str, tool: Tool, emit: Emit) -> ArchiveContents:
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


def _safe_member(
    tarinfo: tarfile.TarInfo, destination: str
) -> tarfile.TarInfo | None:
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


def extract(path: str, destination: str, tool: Tool, emit: Emit) -> None:
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


def _extract_with_tool(path: str, args: list[str], progress: Progress) -> None:
    with tempfile.TemporaryFile() as stderr, open(path, "rb") as fp:
        try:
            process = subprocess.Popen(
                args, stdin=subprocess.PIPE, stderr=stderr
            )
        except OSError as exc:
            raise ArchiveError(f"{args[0]}: {exc}") from None
        assert process.stdin is not None, "stdin is a pipe"
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


def _extract_with_tarfile(
    path: str, destination: str, progress: Progress
) -> None:
    try:
        with open(path, "rb") as fp:
            reader = CountingReader(fp, progress)
            # a stream: tarfile only reads it
            stream = cast("IO[bytes]", reader)
            with tarfile.open(fileobj=stream, mode="r|*") as tar:
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


# qemu-img

PERCENT = re.compile(rb"\(\s*([0-9.]+)/100%\)")


class QemuImg:
    """
    qemu-img, run by the process: info, convert and commit with progress,
    rebase.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def _run(
        self, args: list[str], on_percent: OnPercent | None = None
    ) -> str:
        try:
            process = subprocess.Popen(
                [self.path, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise ArchiveError(f"qemu-img: {exc}") from None
        # pipes, buffered as Popen makes them by default
        assert isinstance(process.stdout, io.BufferedReader)
        assert process.stderr is not None
        try:
            output = b""
            while chunk := process.stdout.read1(4096):
                output += chunk
                if on_percent is not None:
                    found = PERCENT.findall(chunk)
                    if found:
                        on_percent(float(found[-1]))
            stderr = process.stderr.read()
            code = process.wait()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        if code != 0:
            text = stderr.decode("utf-8", "replace").strip()
            raise ArchiveError(f"qemu-img: {text}")
        return output.decode("utf-8", "replace")

    def info(self, path: str) -> dict[str, Any]:
        return json.loads(self._run(["info", "--output=json", path]))

    def convert(
        self,
        source: str,
        target: str,
        compress: bool,
        backing: tuple[str, str] | None = None,
        on_percent: OnPercent | None = None,
    ) -> None:
        """Copy a qcow2 disk, compressed or not, above backing if given."""

        args = ["convert", "-p", "-O", "qcow2", "-m", "8", "-W"]
        if backing is not None:
            args += ["-B", backing[0], "-F", backing[1]]
        if compress:
            try:
                self._run(
                    [
                        *args,
                        "-c",
                        "-o",
                        "compression_type=zstd",
                        source,
                        target,
                    ],
                    on_percent,
                )
                return
            except ArchiveError as exc:
                # zstd needs QEMU 5.1; zlib works with every version.
                if "compression_type" not in str(exc):
                    raise
            args.append("-c")
        self._run([*args, source, target], on_percent)

    def rebase(self, disk: str, backing: str, backing_format: str) -> None:
        self._run(["rebase", "-u", "-b", backing, "-F", backing_format, disk])

    def commit(self, disk: str, on_percent: OnPercent | None = None) -> None:
        """Write the changes of disk into its backing file."""

        self._run(["commit", "-p", disk], on_percent)


def backing_of(info: dict[str, Any]) -> tuple[str, str] | None:
    """The backing file of a disk, as (path, format), from qemu-img info."""

    path = info.get("full-backing-filename") or info.get("backing-filename")
    if not path:
        return None
    return str(path), str(info.get("backing-filename-format", "qcow2"))


# Writing


def data_regions(fd: int, size: int) -> list[tuple[int, int]]:
    """The (offset, length) of the data of a file, without its holes."""

    regions = []
    position = 0
    while position < size:
        try:
            start = os.lseek(fd, position, os.SEEK_DATA)
        except OSError as exc:
            # ENXIO: only a hole is left.
            if exc.errno == errno.ENXIO:
                break
            raise
        end = os.lseek(fd, start, os.SEEK_HOLE)
        regions.append((start, end - start))
        position = end
    return regions


def stored_size(path: str) -> int:
    """The bytes of a file an archive stores: its data, not its holes."""

    fd = os.open(path, os.O_RDONLY)
    try:
        size = os.fstat(fd).st_size
        return sum(length for _, length in data_regions(fd, size))
    finally:
        os.close(fd)


class _SparseData:
    """The data of a GNU sparse 1.0 member: its map, then its data."""

    def __init__(self, fd: int, regions: list[tuple[int, int]]) -> None:
        lines = [str(len(regions))]
        for offset, length in regions:
            lines += [str(offset), str(length)]
        head = ("\n".join(lines) + "\n").encode("ascii")
        self.head = head + b"\0" * (-len(head) % tarfile.BLOCKSIZE)
        self._chunks = self._read(fd, regions)
        self._buffer = bytearray()

    def _read(
        self, fd: int, regions: list[tuple[int, int]]
    ) -> Iterator[bytes]:
        yield self.head
        for offset, length in regions:
            while length:
                chunk = os.pread(fd, min(length, CHUNK), offset)
                if not chunk:
                    raise OSError(errno.EIO, "the file got shorter")
                yield chunk
                offset += len(chunk)
                length -= len(chunk)

    def read(self, size: int = -1) -> bytes:
        while size < 0 or len(self._buffer) < size:
            try:
                self._buffer += next(self._chunks)
            except StopIteration:
                break
        if size < 0:
            size = len(self._buffer)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data


class _SparseInfo(tarfile.TarInfo):
    """
    A member whose size, if too big for octal, is in its header, base-256.

    tarfile reads a GNU sparse member wrong when its size is in a PAX
    record, as tarfile itself would write it above 8 GiB.
    """

    def create_pax_header(
        self,
        info: Mapping[str, str | int | bytes | Mapping[str, str]],
        encoding: str,
    ) -> bytes:
        size = cast(int, info["size"])
        if size <= OCTAL_SIZE_MAX:
            return super().create_pax_header(info, encoding)
        buf = super().create_pax_header(dict(info, size=0), encoding)
        header = bytearray(buf[-tarfile.BLOCKSIZE :])
        # not in typeshed: tarfile's own number field
        itn = tarfile.itn  # type: ignore[attr-defined]
        header[124:136] = itn(size, 12, tarfile.GNU_FORMAT)
        header[148:156] = b" " * 8
        header[148:155] = b"%06o\0" % sum(header)
        return buf[: -tarfile.BLOCKSIZE] + bytes(header)


def add_sparse(tar: tarfile.TarFile, path: str, arcname: str) -> None:
    """Add a file to tar, as a GNU sparse 1.0 member if it has holes."""

    info = tar.gettarinfo(path, arcname)
    info.uname = info.gname = ""
    fd = os.open(path, os.O_RDONLY)
    try:
        size = info.size
        regions = data_regions(fd, size)
        stored = sum(length for _, length in regions)
        if stored == size:
            with os.fdopen(os.dup(fd), "rb") as fp:
                fp.seek(0)
                tar.addfile(info, fp)
            return
        # an empty region at the end gives the size of a file ending in a hole
        if not regions or sum(regions[-1]) < size:
            regions.append((size, 0))
        data = _SparseData(fd, regions)
        sparse = _SparseInfo(
            posixpath.join(
                posixpath.dirname(arcname),
                "GNUSparseFile.0",
                posixpath.basename(arcname),
            )
        )
        sparse.mode, sparse.mtime = info.mode, info.mtime
        sparse.uid, sparse.gid = info.uid, info.gid
        sparse.pax_headers = {
            "GNU.sparse.major": "1",
            "GNU.sparse.minor": "0",
            "GNU.sparse.name": arcname,
            "GNU.sparse.realsize": str(size),
        }
        sparse.size = len(data.head) + stored
        tar.addfile(sparse, data)
    finally:
        os.close(fd)


def outside_images(files: Iterable[str], report: Report) -> list[str]:
    """
    The files but those in a folder of the images, which an import would
    take for images; each folder left out is reported.
    """

    kept = []
    left_out = set()
    for name in files:
        folder, sep, _rest = normalize(name).partition("/")
        if sep and folder in (IMAGES, LEGACY_IMAGES):
            left_out.add(folder)
        else:
            kept.append(name)
    for folder in sorted(left_out):
        report.warning(
            f"left out: an archive keeps its images in {folder}/", folder
        )
    return kept


def order_members(
    project: str, files: Iterable[str], images: Iterable[Sequence[str]]
) -> list[Entry]:
    """
    (arcname, path, kind) of each member, in the order of a new archive.

    contents.toml's members first: the project file and the README, then
    the other files, the private disks and the images, each the smallest
    first.
    """

    entries: list[Entry] = []
    for name in files:
        path = os.path.join(project, name)
        entries.append((name, path, member_kind(name)))
    for image, path in images:
        entries.append((f"{IMAGES}/{image}", str(path), IMAGE))
    rank = {PROJECT: 0, README_KIND: 1, OTHER: 2, DISK: 3, IMAGE: 4}

    def key(entry: Entry) -> tuple[int, int, str]:
        name, path, kind = entry
        return (rank.get(kind, 2), os.path.getsize(path), name)

    return sorted(entries, key=key)


class _Output:
    """The compressed archive, fed with the tar stream; counts its bytes."""

    def __init__(self, path: str, progress: Progress, compress: bool):
        self.fp = open(path, "wb")
        self.progress = progress
        self.gzip = (
            gzip.GzipFile(fileobj=self.fp, mode="wb", mtime=0)
            if compress
            else None
        )

    def write(self, data: bytes) -> int:
        (self.gzip or self.fp).write(data)
        self.progress.advance(len(data))
        return len(data)

    def close(self) -> None:
        if self.gzip is not None:
            self.gzip.close()
        self.fp.close()


def write_archive(job: Table, emit: Emit, tool: Tool) -> dict[str, Any]:
    """Write a project to an archive, in a temporary file renamed at the end."""

    project = str(job["project"])
    output = str(job["output"])
    folder = os.path.dirname(output) or "."
    compress = job.get("compression", "gzip") == "gzip"
    qemu_img = QemuImg(str(job["qemu_img"])) if job.get("qemu_img") else None
    report = Report()
    # as export_project() writes them
    files = outside_images(cast("list[str]", job.get("files", [])), report)
    images = cast("list[list[str]]", job.get("images", []))
    entries = order_members(project, files, images)
    fd, part = tempfile.mkstemp(
        prefix=f".{os.path.basename(output)}.", suffix=".part", dir=folder
    )
    os.close(fd)
    emit({"created": part})
    # Next to the archive: the packed disks can be large.
    staging = tempfile.mkdtemp(prefix=".virtualbricks-export-", dir=folder)
    emit({"created": staging})
    try:
        members = _stage(entries, staging, qemu_img, emit, report)
        with open(os.path.join(staging, CONTENTS), "w") as fp:
            fp.write(write_contents(members))
        names = [CONTENTS] + [m.name for m in members]
        total = sum(stored_size(os.path.join(staging, name)) for name in names)
        progress = Progress(emit, "write", total)
        out = _Output(part, progress, compress)
        try:
            if tool.name == TARFILE:
                _write_with_tarfile(staging, names, out)
            else:
                _write_with_tool(tool, staging, names, out)
        finally:
            out.close()
        progress.done = progress.total
        progress.send()
        os.replace(part, output)
    except BaseException:
        if os.path.lexists(part):
            os.remove(part)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {
        "output": output,
        "size": os.path.getsize(output),
        "report": report_to_list(report),
    }


# A qcow2 disk to pack: (arcname, path, kind, target, its qemu-img info).
_Packing = tuple[str, str, str, str, dict[str, Any]]


def _stage(
    entries: list[Entry],
    staging: str,
    qemu_img: QemuImg | None,
    emit: Emit,
    report: Report,
) -> list[Member]:
    """
    Put the members in staging under their names in the archive.

    The qcow2 disks are packed there by qemu-img, each keeping its backing
    file; the other files are links to themselves.
    """

    packing: list[_Packing] = []
    members = []
    for name, path, kind in entries:
        target = os.path.join(staging, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        info = None
        if qemu_img is not None and kind in (DISK, IMAGE):
            try:
                info = qemu_img.info(path)
            except ArchiveError as exc:
                report.warning(f"stored as it is: {exc}", name)
        if info is not None and info.get("format") == "qcow2":
            packing.append((name, path, kind, target, info))
        else:
            os.symlink(os.path.abspath(path), target)
        members.append((name, path, kind))
    packed: dict[str, int] = {}
    if qemu_img is not None:
        packed = _pack(qemu_img, packing, emit, report)
    return [
        Member(
            name,
            os.path.getsize(os.path.join(staging, name)),
            kind,
            name in packed,
            packed.get(name, 0),
        )
        for name, path, kind in members
    ]


def _pack(
    qemu_img: QemuImg, packing: list[_Packing], emit: Emit, report: Report
) -> dict[str, int]:
    """Pack the qcow2 disks; the size of each one packed, before."""

    total = sum(stored_size(path) for _, path, _, _, _ in packing)
    progress = Progress(emit, "pack", total)
    packed = {}
    for name, path, kind, target, info in packing:
        size = stored_size(path)
        start = progress.done

        def on_percent(
            percent: float, start: int = start, size: int = size
        ) -> None:
            progress.done = start
            progress.advance(int(size * percent / 100))

        try:
            qemu_img.convert(path, target, True, backing_of(info), on_percent)
        except ArchiveError as exc:
            # as when its image is gone: qemu-img can't read the disk
            report.warning(f"stored as it is: {exc}", name)
            if os.path.lexists(target):
                os.remove(target)
            os.symlink(os.path.abspath(path), target)
        else:
            packed[name] = os.path.getsize(path)
        progress.done = start + size
    if packing:
        progress.send()
    return packed


def _write_with_tarfile(staging: str, names: list[str], out: _Output) -> None:
    # a stream: tarfile only writes to it
    stream = cast("IO[bytes]", out)
    with tarfile.open(
        fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT
    ) as tar:
        for name in names:
            add_sparse(
                tar, os.path.realpath(os.path.join(staging, name)), name
            )


def _write_with_tool(
    tool: Tool, staging: str, names: list[str], out: _Output
) -> None:
    if tool.name == BSDTAR:
        args = [tool.path, "-c", "-L", "--format", "pax", "-f", "-"]
    else:
        args = [
            tool.path,
            "-c",
            "--sparse",
            "--dereference",
            "--format=posix",
            "-f",
            "-",
        ]
    args += ["-C", staging, "--", *names]
    with tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=stderr
            )
        except OSError as exc:
            raise ArchiveError(f"{args[0]}: {exc}") from None
        assert process.stdout is not None, "stdout is a pipe"
        try:
            while chunk := process.stdout.read(CHUNK):
                out.write(chunk)
            code = process.wait()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        if code != 0:
            stderr.seek(0)
            text = stderr.read().decode("utf-8", "replace").strip()
            raise ArchiveError(f"{os.path.basename(args[0])}: {text}")


# The jobs on disk images


def _percent_progress(emit: Emit, step: str) -> tuple[Progress, OnPercent]:
    """A Progress in percent, and what qemu-img's percent gives it."""

    progress = Progress(emit, step, 100)

    def on_percent(percent: float) -> None:
        progress.done = 0
        progress.advance(int(percent))

    return progress, on_percent


def _qemu_img(job: Table) -> QemuImg:
    path = str(job.get("qemu_img", ""))
    if not path:
        raise ArchiveError("qemu-img is needed")
    return QemuImg(path)


def write_image(job: Table, emit: Emit) -> dict[str, Any]:
    """
    Write a disk, with the images below it, as a new qcow2 image of its
    own. A job stopped halfway leaves no file.
    """

    qemu_img = _qemu_img(job)
    disk, output = str(job["disk"]), str(job["output"])
    if os.path.lexists(output):
        raise ArchiveError(f"{output} is there already")
    emit({"created": output})
    progress, on_percent = _percent_progress(emit, "save")
    try:
        qemu_img.convert(disk, output, False, None, on_percent)
    except BaseException:
        if os.path.lexists(output):
            os.remove(output)
        raise
    progress.done = 100
    progress.send()
    return {"output": output, "size": stored_size(output)}


def commit_image(job: Table, emit: Emit) -> dict[str, Any]:
    """
    Write the changes of a disk into its image. Stopped halfway, the image
    has part of them, and the disk all of them still.
    """

    qemu_img = _qemu_img(job)
    disk = str(job["disk"])
    progress, on_percent = _percent_progress(emit, "merge")
    qemu_img.commit(disk, on_percent)
    progress.done = 100
    progress.send()
    return {"disk": disk}


# The process


def _on_sigterm(signum: int, frame: FrameType | None) -> NoReturn:
    raise ArchiveCancelled()


def run_job(
    job: Table, emit: Emit, tool: Tool | None = None
) -> dict[str, Any]:
    """Run a job of the process and return its result."""

    if tool is None:
        tool = find_tool()
    kind = job.get("job")
    if kind == "inspect":
        return inspect(str(job["archive"]), tool, emit).to_table()
    if kind == "export":
        return write_archive(job, emit, tool)
    if kind == "import":
        # Imported here: importing uses the reading above.
        from virtualbricks.config.importing import run_import

        return run_import(job, emit, tool)
    if kind == "write-image":
        return write_image(job, emit)
    if kind == "commit-image":
        return commit_image(job, emit)
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
        job = loads_toml(stdin.read())
        emit({"result": run_job(job, emit)})
    except ArchiveCancelled:
        return 1
    except ArchiveError as exc:
        emit({"error": str(exc)})
        return 2
    except Exception:
        emit({"error": traceback.format_exc()})
        return 3
    return 0


# The application's side

# The process runs this module, with python -m.
MODULE = "virtualbricks.config.archive"


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
        self.done: defer.Deferred[Any] = defer.Deferred()
        self.cancelled = False
        self.protocol = _ArchiveProtocol(self)
        self._result: Any = None
        self._has_result = False
        self._error: str | None = None

    def start(self, reactor: IReactorProcess | None = None) -> ArchiveJob:
        if reactor is None:
            from twisted.internet import reactor as default

            reactor = cast("IReactorProcess", default)
        reactor.spawnProcess(
            self.protocol,
            sys.executable,
            [sys.executable, "-m", MODULE],
            env=dict(os.environ),
        )
        return self

    def cancel(self) -> None:
        self.cancelled = True
        self.protocol.terminate()

    # From the protocol

    def connected(self, transport: IProcessTransport) -> None:
        transport.write(dumps_toml(self.job).encode("utf-8"))
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
            self.done.errback(ArchiveCancelled())
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
        assert self.transport is not None, "the process is connected"
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
        if self._running and self.transport is not None:
            try:
                self.transport.signalProcess("TERM")
            except Exception:
                pass

    def processEnded(self, reason: Failure) -> None:
        self._running = False
        self.job.ended(self._stderr.decode("utf-8", "replace"))


def inspect_archive(
    path: str,
    on_head: Callable[[ArchiveContents], None] | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    reactor: IReactorProcess | None = None,
) -> ArchiveJob:
    """Read an archive in the process; done fires with ArchiveContents."""

    def head(table: dict[str, Any]) -> None:
        if on_head is not None:
            on_head(ArchiveContents.from_table(table))

    job = ArchiveJob(
        {"job": "inspect", "archive": path}, on_progress, head
    ).start(reactor)
    job.done.addCallback(ArchiveContents.from_table)
    return job


def find_qemu_img() -> str:
    """The qemu-img of the settings or of PATH; "" if there's none."""

    from virtualbricks.qemu import run

    try:
        return run.which("qemu-img")
    except FileNotFoundError:
        return ""


def export_project(
    project: str,
    output: str,
    files: Iterable[str],
    images: Iterable[tuple[str, str]] = (),
    on_progress: Callable[[str, int, int], None] | None = None,
    qemu_img: str = "",
    reactor: IReactorProcess | None = None,
) -> ArchiveJob:
    """
    Write an archive of the project in the process.

    files are relative to the project's folder; images are (name, path).
    done fires with {"output": ..., "size": ...}.
    """

    job = ArchiveJob(
        {
            "job": "export",
            "project": project,
            "output": output,
            "files": list(files),
            "images": [[name, path] for name, path in images],
            # The qcow2 disks are compressed by qemu-img, so the archive
            # isn't; without qemu-img the archive is gzipped instead.
            "compression": "none" if qemu_img else "gzip",
            "qemu_img": qemu_img,
        },
        on_progress,
    )
    return job.start(reactor)


def save_image(
    disk: str,
    output: str,
    on_progress: Callable[[str, int, int], None] | None = None,
    qemu_img: str = "",
    reactor: IReactorProcess | None = None,
) -> ArchiveJob:
    """
    Write disk, with its changes, as the new image output, in the process.
    done fires with {"output": ..., "size": ...}.
    """

    job = ArchiveJob(
        {
            "job": "write-image",
            "disk": disk,
            "output": output,
            "qemu_img": qemu_img or find_qemu_img(),
        },
        on_progress,
    )
    return job.start(reactor)


def merge_image(
    disk: str,
    on_progress: Callable[[str, int, int], None] | None = None,
    qemu_img: str = "",
    reactor: IReactorProcess | None = None,
) -> ArchiveJob:
    """Write the changes of disk into its image, in the process."""

    job = ArchiveJob(
        {
            "job": "commit-image",
            "disk": disk,
            "qemu_img": qemu_img or find_qemu_img(),
        },
        on_progress,
    )
    return job.start(reactor)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
