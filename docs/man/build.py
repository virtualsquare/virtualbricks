#!/usr/bin/env python3
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team
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
Build the man pages from their Markdown sources with pandoc.

    docs/man/<page>.<section>.md    source, pandoc's Markdown
    docs/man/<page>.<section>       man page, committed like the catalogs

VERSION and DATE in the metadata of a source become the version of
Virtualbricks and the date of the page. The date changes only when the page
does, or comes from SOURCE_DATE_EPOCH: running the script twice in a row leaves
the tree untouched. With --check it writes nothing and exits with 1 if a page
is out of date.

It uses the pandoc of the pypandoc-binary package if it's installed, as in the
pre-commit hook and the dev dependency group, so that everyone builds with the
same version, or else the pandoc on the PATH.
"""

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SOURCE = re.compile(r"^(?P<page>.+)\.(?P<section>[1-9])\.md$")
FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
# The title line of the page, with the date; see today() and body().
TITLE = re.compile(r"^\.TH .*$", re.MULTILINE)
PANDOC_OPTIONS = [
    "--standalone",
    # "--" must stay two hyphens in options such as --in-place, and
    # "[settings]" must not become a link to the SETTINGS section
    "--from=markdown-smart-implicit_header_references",
    "--to=man",
]


class Error(Exception):
    pass


def pandoc_path():
    try:
        import pypandoc

        path = pypandoc.get_pandoc_path()
    except (ImportError, OSError):
        path = shutil.which("pandoc")
    if path is None:
        raise Error(
            "pandoc not found: install the dev dependency group, or pandoc"
        )
    return path


def version():
    path = os.path.join(ROOT, "virtualbricks", "__init__.py")
    with open(path, encoding="utf-8") as fp:
        match = re.search(r"^__version__ = ['\"](.*)['\"]$", fp.read(), re.M)
    return match.group(1)


def today():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        moment = datetime.datetime.fromtimestamp(
            int(epoch), datetime.timezone.utc
        )
        return moment.date().isoformat()
    return datetime.date.today().isoformat()


def render(pandoc, source, date):
    with open(source, encoding="utf-8") as fp:
        text = fp.read()
    match = FRONT_MATTER.match(text)
    if match is None:
        raise Error(f"{source}: no metadata block at the top")
    metadata = match.group(0).replace("VERSION", version())
    text = metadata.replace("DATE", date) + text[match.end() :]
    result = subprocess.run(
        [pandoc, *PANDOC_OPTIONS],
        input=text,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise Error(f"{source}: {result.stderr.strip()}")
    return result.stdout


def body(page):
    """The page without its title line, which holds the date."""

    return TITLE.sub("", page, count=1)


def build(pandoc, source, target, check=False):
    """Build a page; return True if the target is, or was, out of date."""

    current = None
    if os.path.exists(target):
        with open(target, encoding="utf-8") as fp:
            current = fp.read()
    page = render(pandoc, source, today())
    if current is not None and body(current) == body(page):
        if "SOURCE_DATE_EPOCH" not in os.environ or current == page:
            return False
    if not check:
        with open(target, "w", encoding="utf-8") as fp:
            fp.write(page)
    return True


def sources():
    for name in sorted(os.listdir(HERE)):
        if SOURCE.match(name):
            yield os.path.join(HERE, name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing, exit with 1 if a page is out of date",
    )
    args = parser.parse_args(argv)
    try:
        pandoc = pandoc_path()
        stale = []
        for source in sources():
            target = source[: -len(".md")]
            if build(pandoc, source, target, args.check):
                stale.append(os.path.relpath(target, ROOT))
    except Error as exc:
        print(f"build.py: {exc}", file=sys.stderr)
        return 2
    for path in stale:
        print(f"{path} is out of date" if args.check else f"built {path}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
