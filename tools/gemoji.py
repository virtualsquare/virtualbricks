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
The names of the emoji of GitHub, as :smile:, into virtualbricks/emoji.py.

    python tools/gemoji.py                  db/emoji.json of gemoji's master
    python tools/gemoji.py emoji.json       a db/emoji.json at hand

gemoji is the library of GitHub for its emoji; its db/emoji.json has each
emoji with its names. The module has them all, a name to its emoji, sorted
by name, with the license of gemoji. A character that doesn't show, as the
joiner of the three in 🧑‍💻, is written as an escape.
"""

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODULE = os.path.join(ROOT, "virtualbricks", "emoji.py")
SOURCE = "https://raw.githubusercontent.com/github/gemoji/master/db/emoji.json"
# The license of gemoji, which goes with its names.
LICENSE = """\
Copyright (c) 2019 GitHub, Inc.

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
"""
HEADER = '''\
# The names of the emoji of GitHub, from db/emoji.json of gemoji,
# https://github.com/github/gemoji, under its license:
#
{license}
"""
The emoji of GitHub by their names, without the colons: "smile" is 😄.

Written by tools/gemoji.py; run it again for the emoji that GitHub adds.
"""

NAMES: dict[str, str] = {{
'''


def literal(text: str) -> str:
    """A string in double quotes, with what doesn't show as an escape."""

    chars = (
        char if char.isprintable() else f"\\u{ord(char):04x}" for char in text
    )
    return '"' + "".join(chars) + '"'


def names(entries: list[dict[str, object]]) -> dict[str, str]:
    """Each name of db/emoji.json, and its emoji."""

    result: dict[str, str] = {}
    for entry in entries:
        emoji = entry["emoji"]
        aliases = entry["aliases"]
        assert isinstance(emoji, str) and isinstance(aliases, list)
        for alias in aliases:
            result[str(alias)] = emoji
    return result


def module(emoji: dict[str, str]) -> str:
    """The source of virtualbricks/emoji.py."""

    license = "\n".join(
        f"# {line}" if line else "#" for line in LICENSE.splitlines()
    )
    lines = [HEADER.format(license=license)]
    for name in sorted(emoji):
        lines.append(f"    {literal(name)}: {literal(emoji[name])},\n")
    lines.append("}\n")
    return "".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The names of the emoji of GitHub, into "
        "virtualbricks/emoji.py."
    )
    parser.add_argument(
        "json",
        nargs="?",
        metavar="JSON",
        help="a db/emoji.json of gemoji (default: that of its master)",
    )
    args = parser.parse_args(argv)
    if args.json is None:
        with urllib.request.urlopen(SOURCE, timeout=60) as response:
            entries = json.load(response)
    else:
        with open(args.json, encoding="utf-8") as fp:
            entries = json.load(fp)
    emoji = names(entries)
    with open(MODULE, "w", encoding="utf-8") as fp:
        fp.write(module(emoji))
    print(f"{len(emoji)} names of {len(entries)} emoji in {MODULE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
