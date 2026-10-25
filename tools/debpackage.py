#!/usr/bin/env python3
# -*- test-case-name: virtualbricks.tests.test_tools -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team
#
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
The Debian packages, built and checked in a container of each supported
distribution, as the pipeline of GitLab builds them:

    python tools/debpackage.py                          every distribution
    python tools/debpackage.py debian-13 ubuntu-24.04
    python tools/debpackage.py --key KEYID              signed with KEYID

The upstream tarball is the sdist of the files that Git tracks, as they are
in the folder, edits and all: one, the same for every distribution. The
debian/ folder is the one of the checkout: --debian names another. Each
distribution builds the package, as virtualbricks_3.0.0~dev8-0~trixie1: the
version of Virtualbricks, where a pre-release comes before its release. Then
its lintian checks the upload, and an error or a warning fails it; a new
container installs the package with what it depends on, an empty package in
place of vde-netemu, which the distributions don't have; as a user that isn't
root, the console makes a switch, and the windows are still open after 15 s
under xvfb.

With --key, debsign signs the .changes, the .dsc and the .buildinfo here,
with the key of gpg, which never goes in a container, and gpgv checks the
signatures; without, the packages are unsigned. The packages that passed go
to --out, dist/debian by default. The folder of a distribution that failed
stays, with its logs and its files. The distributions build side by side;
the exit status is 1 if one failed. It needs podman and the network, and
debsign (devscripts) and gpgv for --key. --sdist gives the upstream tarball
instead.

The pipeline runs the steps with --here, in the container of each job, as
root, with no podman, and shows their output:

    python3 tools/debpackage.py --here sdist --out sdist
    python3 tools/debpackage.py --here build --sdist FILE --out dist debian-13

The first makes the sdist of the checkout, the second builds the package of
one distribution from it and runs lintian; the package isn't installed.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class Target(NamedTuple):
    image: str
    codename: str


# The supported distributions, as the jobs of the pipeline name them, and the
# name of each in the changelog and in the repository.
TARGETS: dict[str, Target] = {
    "debian-13": Target("docker.io/library/debian:trixie", "trixie"),
    "debian-14": Target("docker.io/library/debian:forky", "forky"),
    "debian-sid": Target("docker.io/library/debian:sid", "sid"),
    "ubuntu-24.04": Target("docker.io/library/ubuntu:24.04", "noble"),
    "ubuntu-26.04": Target("docker.io/library/ubuntu:26.04", "resolute"),
}
# The sdist is made on Debian 13, the oldest that has setuptools 77.
SOURCE = TARGETS["debian-13"].image
# The exit statuses of INSTALL before its end.
NO_INSTALL = 10
NO_CONSOLE = 11
NO_WINDOWS = 12
# The mode that Git gives a submodule in its index.
SUBMODULE = "160000"

# As root: the files of $1 copied; their sdist in $2.
SDIST = """\
set -eu
export DEBIAN_FRONTEND=noninteractive
src=$1 out=$2
apt-get update
apt-get install -y --no-install-recommends python3-build python3-setuptools
copy=$(mktemp -d)
cp -R "$src/." "$copy"
cd "$copy"
python3 -m build --sdist --no-isolation --outdir "$out" .
"""
# As root: the sdist $1 as the upstream tarball, with the debian/ folder $2;
# the files of the upload in $3, then what lintian says of them. $4 is the
# upstream version, $5 the Debian one, $6 the codename.
BUILD = """\
set -eu
export DEBIAN_FRONTEND=noninteractive
sdist=$1 debian=$2 out=$3 upstream=$4 version=$5 codename=$6
apt-get update
cd "$(mktemp -d)"
cp "$sdist" "virtualbricks_$upstream.orig.tar.gz"
mkdir "virtualbricks-$upstream"
tar -xzf "virtualbricks_$upstream.orig.tar.gz" --strip-components=1 \\
    -C "virtualbricks-$upstream"
cp -R "$debian" "virtualbricks-$upstream/debian"
cd "virtualbricks-$upstream"
apt-get build-dep -y --no-install-recommends ./
apt-get install -y --no-install-recommends devscripts lintian
# pyproject.toml needs setuptools 77 or newer, with packaging 24.2 or newer,
# which Ubuntu 24.04 doesn't have (68.1 and 24.0): there they come from PyPI
python3 -c 'import setuptools, sys
sys.exit(int(setuptools.__version__.split(".")[0]) < 77)' || {
    apt-get install -y --no-install-recommends python3-pip
    pip3 install --break-system-packages --ignore-installed \\
        'setuptools>=77' 'packaging>=24.2'
}
# the changelog by the Maintainer of debian/control
DEBEMAIL=$(sed -n 's/^Maintainer: //p' debian/control)
export DEBEMAIL
debchange --newversion "$version" "New upstream version"
debchange --release --distribution "$codename" ""
dpkg-buildpackage --no-sign
cp "../virtualbricks_$upstream.orig.tar.gz" "../virtualbricks_$version"* \\
    "$out/"
status=0
# a lintian older than the Standards-Version of debian/control says so: the
# package isn't wrong for that
lintian --fail-on error,warning --info \\
    --suppress-tags newer-standards-version "$out"/*.changes \\
    >"$out/lintian.log" 2>&1 || status=$?
echo "$status" >"$out/lintian.status"
"""
# As root: the package in $1, with what it depends on; then the script $2 as
# another user.
INSTALL = f"""\
set -u
export DEBIAN_FRONTEND=noninteractive
debs=$1 check=$2
apt-get update || exit {NO_INSTALL}
mkdir -p /tmp/vde-netemu/DEBIAN
cat >/tmp/vde-netemu/DEBIAN/control <<'EOF'
Package: vde-netemu
Version: 0
Architecture: all
Maintainer: debpackage <root@localhost>
Description: an empty package in place of vde-netemu
EOF
dpkg-deb --build /tmp/vde-netemu /tmp/vde-netemu.deb || exit {NO_INSTALL}
apt-get install -y --no-install-recommends /tmp/vde-netemu.deb xvfb xauth \\
    "$debs"/virtualbricks_*_all.deb || exit {NO_INSTALL}
useradd -m tester
runuser -u tester -- sh -c "$check"
"""
# As the user: the console makes a switch, the windows stay open.
CHECK = f"""\
set -u
export HOME=/home/tester LC_ALL=C.UTF-8 XDG_RUNTIME_DIR="$(mktemp -d)"
cd "$HOME"
printf 'brick new switch\\nbrick list\\nquit\\n' |
    timeout 60 virtualbricks --no-gui --workspace "$HOME/workspace" \\
    >console.log 2>&1
status=$?
echo "the console ($status):"
cat console.log
test "$status" = 0 || exit {NO_CONSOLE}
awk '$1 == "sw1" && $2 == "Switch" {{found = 1}} END {{exit !found}}' \\
    console.log || exit {NO_CONSOLE}
xvfb-run -a timeout 15 virtualbricks --no-term </dev/null >gui.log 2>&1
status=$?
echo "the windows ($status):"
cat gui.log
test "$status" = 124 || exit {NO_WINDOWS}
if grep -q Traceback gui.log; then exit {NO_WINDOWS}; fi
"""


class Volume(NamedTuple):
    """A folder of this computer, host, at path in a container."""

    host: str
    path: str
    readonly: bool = False


class Result(NamedTuple):
    """What a distribution did: if it passed, the lines that say it, the
    folder with its files."""

    passed: bool
    lines: list[str]
    folder: str


def debian_version(version: str) -> str:
    """The upstream version of Debian of a version of Python: a pre-release
    with a tilde, which comes before what has nothing after it. As in the
    pipeline, whose versions are the same: Debian puts 3.0.0.dev8 after
    3.0.0a1 and 3.0.0b1, not before them."""

    return re.sub(r"\.?(dev|a|b|rc)(\d+)", r"~\1\2", version)


def sdist_version(path: str) -> str:
    """The version in the PKG-INFO of the sdist at path."""

    with tarfile.open(path) as tar:
        for member in tar.getmembers():
            if member.name.count("/") == 1 and member.name.endswith(
                "/PKG-INFO"
            ):
                fp = tar.extractfile(member)
                assert fp is not None
                for line in fp.read().decode("utf-8").splitlines():
                    if line.startswith("Version: "):
                        return line.removeprefix("Version: ").strip()
    raise ValueError(f"no version in {path}")


def tracked(root: str) -> list[str]:
    """The files of root that Git tracks and that are there; not its
    submodules, as the theme of the site, which are folders."""

    entries = subprocess.run(
        ["git", "-C", root, "ls-files", "-z", "--stage"],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    names = []
    for entry in entries.split("\0"):
        if not entry:
            continue
        # mode, object and stage, a tab, the path
        info, name = entry.split("\t", 1)
        if info.split()[0] == SUBMODULE:
            continue
        if os.path.lexists(os.path.join(root, name)):
            names.append(name)
    return names


def copy_tracked(root: str, folder: str) -> None:
    for name in tracked(root):
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copy2(os.path.join(root, name), path, follow_symlinks=False)


def lfs_pointers(folder: str) -> list[str]:
    """The pictures under folder that are pointers of Git LFS: the checkout
    has not their files."""

    pointers = []
    for path in sorted(glob.glob(f"{folder}/**/*.png", recursive=True)):
        with open(path, "rb") as fp:
            if fp.read(24) == b"version https://git-lfs.":
                pointers.append(os.path.relpath(path, folder))
    return pointers


def lintian_tags(log: str) -> list[str]:
    """The errors and the warnings in the log of lintian."""

    return [line for line in log.splitlines() if line[:3] in ("E: ", "W: ")]


def _read(folder: str, name: str) -> str:
    try:
        with open(os.path.join(folder, name), encoding="utf-8") as fp:
            return fp.read()
    except FileNotFoundError:
        return ""


def podman(
    image: str,
    volumes: Sequence[Volume],
    script: str,
    args: Sequence[str],
    log: str,
) -> int:
    """sh runs script with args in a container of image, with the volumes,
    its output in log: its exit status."""

    with open(log, "w", encoding="utf-8") as fp:
        return subprocess.run(
            ["podman", "run", "--rm"]
            + [
                f"--volume={volume.host}:{volume.path}"
                + (":ro" if volume.readonly else "")
                for volume in volumes
            ]
            + [image, "sh", "-c", script, "sh", *args],
            stdin=subprocess.DEVNULL,
            stdout=fp,
            stderr=subprocess.STDOUT,
        ).returncode


def on_host(arg: str, volumes: Sequence[Volume]) -> str:
    """arg, if a path in a volume, as the path of its folder."""

    for volume in volumes:
        if arg == volume.path or arg.startswith(volume.path + "/"):
            return volume.host + arg[len(volume.path) :]
    return arg


def in_this_system(
    volumes: Sequence[Volume], script: str, args: Sequence[str], log: str
) -> int:
    """sh runs script with args here, the paths of the volumes their
    folders; its output in log and on stdout: its exit status."""

    process = subprocess.Popen(
        ["sh", "-c", script, "sh", *(on_host(arg, volumes) for arg in args)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert process.stdout is not None
    with open(log, "wb") as fp:
        for line in process.stdout:
            fp.write(line)
            sys.stdout.write(line.decode("utf-8", "replace"))
            sys.stdout.flush()
    return process.wait()


def run(
    here: bool,
    image: str,
    volumes: Sequence[Volume],
    script: str,
    args: Sequence[str],
    log: str,
) -> int:
    """A step: in a container of image, or in this system if here."""

    if here:
        return in_this_system(volumes, script, args, log)
    return podman(image, volumes, script, args, log)


def source(here: bool, work: str) -> tuple[str | None, list[str]]:
    """The sdist, in a folder of work: its path, or None and the lines that
    say why. In a container, of the files of ROOT that Git tracks; here, of
    ROOT."""

    if here:
        src = ROOT
    else:
        src = os.path.join(work, "src")
        copy_tracked(ROOT, src)
    pointers = lfs_pointers(src)
    if pointers:
        return None, [
            f"the pictures of Git LFS are missing, as {pointers[0]}:"
            " `git lfs pull`"
        ]
    out = os.path.join(work, "sdist")
    os.makedirs(out)
    status = run(
        here,
        SOURCE,
        [Volume(src, "/src", True), Volume(out, "/out")],
        SDIST,
        ["/src", "/out"],
        os.path.join(work, "sdist.log"),
    )
    if not here:
        shutil.rmtree(src)
    made = glob.glob(os.path.join(out, "virtualbricks-*.tar.gz"))
    if status != 0 or len(made) != 1:
        return None, [f"the sdist failed ({status}): sdist.log"]
    return made[0], []


def build(
    here: bool,
    work: str,
    sdist: str,
    upstream: str,
    debian: str,
    target: str,
) -> tuple[Result, bool]:
    """The package of target, built in a folder of work from sdist, and what
    lintian says: its result, and if it was built."""

    image, codename = TARGETS[target]
    version = f"{upstream}-0~{codename}1"
    folder = os.path.join(work, target)
    os.makedirs(folder)
    lines = [f"{target}: virtualbricks {version}"]
    status = run(
        here,
        image,
        [
            Volume(os.path.dirname(sdist), "/sdist", True),
            Volume(debian, "/debian", True),
            Volume(folder, "/out"),
        ],
        BUILD,
        [
            f"/sdist/{os.path.basename(sdist)}",
            "/debian",
            "/out",
            upstream,
            version,
            codename,
        ],
        os.path.join(folder, "build.log"),
    )
    if status != 0:
        lines.append(f"  the build failed ({status}): build.log")
        return Result(False, lines, folder), False
    passed = _read(folder, "lintian.status").strip() == "0"
    tags = lintian_tags(_read(folder, "lintian.log"))
    if passed and not tags:
        lines.append("  lintian: nothing")
    else:
        lines.append("  lintian: failed: lintian.log")
        lines += [f"    {tag}" for tag in tags]
    return Result(passed, lines, folder), True


def installed(result: Result, target: str) -> Result:
    """result, its package installed in a new container of target, as a
    user its console and its windows."""

    status = run(
        False,
        TARGETS[target].image,
        [Volume(result.folder, "/debs", True)],
        INSTALL,
        ["/debs", CHECK],
        os.path.join(result.folder, "install.log"),
    )
    line = {
        0: "  the package: a switch made, the windows open",
        NO_INSTALL: "  the package: not installed: install.log",
        NO_CONSOLE: "  the package: no switch: install.log",
        NO_WINDOWS: "  the package: the windows failed: install.log",
    }.get(status, f"  the package: the container failed ({status})")
    return Result(
        result.passed and status == 0, result.lines + [line], result.folder
    )


def package(
    here: bool,
    work: str,
    sdist: str,
    upstream: str,
    debian: str,
    target: str,
) -> Result:
    """The package of target, built and checked; in a container, installed
    too."""

    result, built = build(here, work, sdist, upstream, debian, target)
    if here or not built:
        return result
    return installed(result, target)


def upload(folder: str) -> list[str]:
    """The files of the upload in folder."""

    return sorted(glob.glob(os.path.join(folder, "virtualbricks_*")))


def sign(key: str, changes: str, log: str) -> bool:
    """debsign signs the .changes, and the .dsc and the .buildinfo that it
    lists, with key, its output in log; gpg may ask the passphrase."""

    with open(log, "w", encoding="utf-8") as fp:
        status = subprocess.run(
            ["debsign", "--re-sign", f"-k{key}", changes],
            stdout=fp,
            stderr=subprocess.STDOUT,
        ).returncode
    return status == 0


def signatures(key: str, paths: Sequence[str], folder: str) -> list[str]:
    """The files of paths without a good signature of key; gpgv writes what
    it says of each in gpgv.log in folder."""

    keyring = os.path.join(folder, "key.gpg")
    with open(keyring, "wb") as fp:
        subprocess.run(["gpg", "--export", key], stdout=fp, check=True)
    bad = []
    with open(os.path.join(folder, "gpgv.log"), "w", encoding="utf-8") as fp:
        for path in paths:
            status = subprocess.run(
                ["gpgv", "--keyring", keyring, path],
                stdout=fp,
                stderr=subprocess.STDOUT,
            ).returncode
            if status != 0:
                bad.append(path)
    return bad


def signed(key: str, result: Result) -> Result:
    """result, its upload signed with key and its signatures checked."""

    files = upload(result.folder)
    [changes] = [path for path in files if path.endswith(".changes")]
    if not sign(key, changes, os.path.join(result.folder, "debsign.log")):
        line = "  the signature: debsign failed: debsign.log"
        return Result(False, result.lines + [line], result.folder)
    paths = [
        path
        for suffix in (".changes", ".dsc", ".buildinfo")
        for path in files
        if path.endswith(suffix)
    ]
    bad = signatures(key, paths, result.folder)
    if bad:
        names = ", ".join(os.path.basename(path) for path in bad)
        line = f"  the signature: bad on {names}: gpgv.log"
        return Result(False, result.lines + [line], result.folder)
    line = f"  the signature: good, {key}"
    return Result(result.passed, result.lines + [line], result.folder)


def has_secret_key(key: str) -> bool:
    return (
        subprocess.run(
            ["gpg", "--list-secret-keys", key],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def refused(args: argparse.Namespace, debian: str) -> str | None:
    """Why the arguments can't build, or None."""

    unknown = sorted(set(args.targets) - set(TARGETS))
    if unknown:
        return f"unknown distributions: {', '.join(unknown)}"
    if args.here is None:
        if shutil.which("podman") is None:
            return "podman isn't installed"
    elif os.geteuid() != 0:
        return f"--here {args.here} installs packages: run it as root"
    elif args.here == "sdist":
        if args.targets or args.sdist is not None:
            return "--here sdist takes no distribution and no --sdist"
        return None
    elif len(args.targets) != 1 or args.sdist is None:
        return "--here build takes one distribution and --sdist"
    if args.sdist is not None and not os.path.isfile(args.sdist):
        return f"no sdist {args.sdist}"
    if not os.path.exists(os.path.join(debian, "control")):
        return f"no control in {debian}"
    if args.key is not None:
        for program in ("debsign", "gpgv"):
            if shutil.which(program) is None:
                return f"{program} isn't installed"
        if not has_secret_key(args.key):
            return f"gpg has no secret key {args.key}"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The Debian packages, built and checked in a container"
        " of each supported distribution."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="DISTRIBUTION",
        help=f"{', '.join(TARGETS)} (default: all of them)",
    )
    parser.add_argument(
        "--key",
        metavar="KEYID",
        help="sign the uploads with this key of gpg (default: unsigned)",
    )
    parser.add_argument(
        "--sdist",
        metavar="FILE",
        help="the upstream tarball (default: the sdist of the checkout)",
    )
    parser.add_argument(
        "--debian",
        metavar="FOLDER",
        help="the debian/ folder (default: the one of the checkout)",
    )
    parser.add_argument(
        "--out",
        metavar="FOLDER",
        help="where the packages that passed go (default: dist/debian;"
        " for --here sdist, dist)",
    )
    parser.add_argument(
        "--here",
        choices=("sdist", "build"),
        help="one step, in this system, a container of the distribution, as"
        " root: the sdist, or the package of one distribution from --sdist,"
        " not installed; the pipeline runs them",
    )
    args = parser.parse_args(argv)
    here = args.here is not None
    if not here:
        args.targets = args.targets or list(TARGETS)
    debian = os.path.abspath(args.debian or os.path.join(ROOT, "debian"))
    folder = ["dist"] if args.here == "sdist" else ["dist", "debian"]
    out = os.path.abspath(args.out or os.path.join(ROOT, *folder))
    reason = refused(args, debian)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 2
    work = tempfile.mkdtemp(prefix="debpackage.")
    if args.sdist is not None:
        sdist = os.path.abspath(args.sdist)
    else:
        print("making the sdist", file=sys.stderr)
        made, lines = source(here, work)
        if made is None:
            print("\n".join(lines + [f"the logs: {work}"]))
            return 1
        sdist = made
    if args.here == "sdist":
        os.makedirs(out, exist_ok=True)
        shutil.copy2(sdist, out)
        shutil.rmtree(work)
        print(f"the sdist: {os.path.join(out, os.path.basename(sdist))}")
        return 0
    upstream = debian_version(sdist_version(sdist))
    print(f"building on {', '.join(args.targets)}", file=sys.stderr)
    with ThreadPoolExecutor(len(args.targets)) as pool:
        results = list(
            pool.map(
                lambda target: package(
                    here, work, sdist, upstream, debian, target
                ),
                args.targets,
            )
        )
    if args.key is not None:
        # one after the other: gpg may ask the passphrase
        results = [
            signed(args.key, result) if result.passed else result
            for result in results
        ]
    os.makedirs(out, exist_ok=True)
    for result in results:
        if result.passed:
            for path in upload(result.folder):
                shutil.copy2(path, out)
            shutil.rmtree(result.folder)
        else:
            result.lines.append(f"  the logs: {result.folder}")
        print("\n".join(result.lines), flush=True)
    if all(result.passed for result in results):
        shutil.rmtree(work)
        print(f"the packages: {out}")
        return 0
    if any(result.passed for result in results):
        print(f"the packages that passed: {out}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
