#!/usr/bin/env python3
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
Check the pages of the user guide and build their HTML with the Yelp tools.

    docs/built/mallard/     the pages, in Mallard, that docs/build.py writes
                            from their Markdown, shown by Yelp; their pictures
                            in figures/
    help/html.xsl           what the HTML adds to the stylesheets of yelp-xsl
    help/html/C/            the HTML of yelp-build, committed like the man
                            pages, for a desktop without Yelp and the website;
                            in figures/, a copy of the pictures it shows

First yelp-check validates each page against the schema of Mallard and looks
for links to pages that aren't there; then yelp-build writes the HTML, and the
script copies into help/html/C/ the files that changed and removes those of
pages that are gone, in figures/ too. Running it twice in a row leaves the
tree untouched. With --check it writes nothing and exits with 1 if the HTML
is out of date.

The HTML depends on the version of yelp-xsl: another version may write other
HTML from the same pages.
"""

import argparse
import filecmp
import glob
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGES = os.path.join(ROOT, "docs", "built", "mallard")
CUSTOM = os.path.join(HERE, "html.xsl")
HTML = os.path.join(HERE, "html", "C")


class Error(Exception):
    pass


def tool(name):
    path = shutil.which(name)
    if path is None:
        raise Error(f"{name} not found: install yelp-tools")
    return path


def pages():
    return sorted(glob.glob(os.path.join(PAGES, "*.page")))


def run(command):
    result = subprocess.run(
        command, capture_output=True, check=False, encoding="utf-8"
    )
    if result.returncode != 0:
        raise Error((result.stdout + result.stderr).strip())


def check_pages():
    """Validate the pages and their links; raise Error with what's wrong."""

    yelp_check = tool("yelp-check")
    run([yelp_check, "validate", *pages()])
    run([yelp_check, "links", PAGES])


def render(folder):
    """Write the HTML of the pages into folder."""

    run(
        [
            tool("yelp-build"),
            "html",
            "-x",
            CUSTOM,
            "-o",
            folder + os.sep,
            PAGES + os.sep,
        ]
    )


def files(folder):
    """The files under folder, as paths relative to it; none if it isn't."""

    found = set()
    for parent, _dirs, names in os.walk(folder):
        for name in names:
            path = os.path.join(parent, name)
            found.add(os.path.relpath(path, folder))
    return found


def differences(built, target):
    """The files of target to write and to remove, to make it built."""

    new = files(built)
    old = files(target)
    write = sorted(
        name
        for name in new
        if name not in old
        or not filecmp.cmp(
            os.path.join(built, name),
            os.path.join(target, name),
            shallow=False,
        )
    )
    return write, sorted(old - new)


def build(check=False):
    """
    Build the HTML; return the files that are, or were, out of date: those
    to write, and those to remove.
    """

    check_pages()
    with tempfile.TemporaryDirectory() as built:
        render(built)
        write, remove = differences(built, HTML)
        if not check:
            for name in write:
                path = os.path.join(HTML, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                shutil.copyfile(os.path.join(built, name), path)
            for name in remove:
                os.remove(os.path.join(HTML, name))
            # the folders left empty, as figures/ without pictures
            for parent, dirs, names in os.walk(HTML, topdown=False):
                if parent != HTML and not dirs and not names:
                    os.rmdir(parent)
    return write, remove


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing, exit with 1 if the HTML is out of date",
    )
    args = parser.parse_args(argv)
    try:
        write, remove = build(args.check)
    except Error as exc:
        print(f"build.py: {exc}", file=sys.stderr)
        return 2
    for names, done in ((write, "built"), (remove, "removed")):
        for name in names:
            path = os.path.relpath(os.path.join(HTML, name), ROOT)
            print(f"{path} is out of date" if args.check else f"{done} {path}")
    return 1 if args.check and (write or remove) else 0


if __name__ == "__main__":
    sys.exit(main())
