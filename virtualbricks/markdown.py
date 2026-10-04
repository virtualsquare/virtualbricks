# -*- test-case-name: virtualbricks.tests.test_markdown -*-
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
The README of a project, read as Markdown.

The README stays a plain text file; what looks like Markdown in it is shown
rendered where the README is only read. The syntax is a subset of CommonMark,
the core that GitHub, GitLab and most editors share:

- headings, ``#`` to ``######``, and titles underlined with ``===`` or
  ``---``;
- paragraphs, where a new line is a line break: a README written as plain
  text keeps its lines;
- ``*italic*``, ``**bold**``, ``~~struck~~``, ```code``` and fenced code
  blocks;
- lists, ``- item`` and ``1. item``, nested by indenting them;
- quotes, ``> text``;
- links: ``[text](url)``, ``<url>``, and an ``http`` or ``https`` URL
  written as it is;
- pictures, ``![text](path)``, where the path is relative to the folder
  of the project: the view shows a picture that is in the folder, and the
  text of any other;
- rules, ``---``.

Anything else stays text: a table, raw HTML, a line indented by four spaces.
The parser is markdown-it-py, from its "zero" preset, where every rule is off,
with only the rules of this syntax on. The renderers walk its tokens; a
``softbreak`` is a line break for them.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

RULES = (
    "heading",
    "lheading",
    "list",
    "blockquote",
    "fence",
    "hr",
    "emphasis",
    "strikethrough",
    "backticks",
    "link",
    "image",
    "autolink",
    "escape",
    "entity",
    "newline",
)
# A URL written as text; it ends before the punctuation that ends a sentence.
BARE_URL = re.compile(r"https?://[^\s<>]*[^\s<>.,;:!?'\")\]]")

_PARSER = MarkdownIt("zero").enable(list(RULES))


def parse(text: str) -> list[Token]:
    """The tokens of a README; the URLs written bare are links."""

    tokens = _PARSER.parse(text)
    for token in tokens:
        if token.type == "inline" and token.children:
            token.children = _link_bare_urls(token.children)
    return tokens


def _text(content: str) -> Token:
    token = Token("text", "", 0)
    token.content = content
    return token


def _link(url: str) -> list[Token]:
    link_open = Token("link_open", "a", 1)
    link_open.attrSet("href", url)
    return [link_open, _text(url), Token("link_close", "a", -1)]


def _link_bare_urls(children: list[Token]) -> list[Token]:
    """Make links of the URLs in the text, outside links and code."""

    result: list[Token] = []
    in_link = 0
    for child in children:
        if child.type == "link_open":
            in_link += 1
        elif child.type == "link_close":
            in_link -= 1
        if child.type != "text" or in_link:
            result.append(child)
            continue
        matches = list(BARE_URL.finditer(child.content))
        if not matches:
            result.append(child)
            continue
        start = 0
        for match in matches:
            if match.start() > start:
                result.append(_text(child.content[start : match.start()]))
            result += _link(match.group())
            start = match.end()
        if start < len(child.content):
            result.append(_text(child.content[start:]))
    return result


def plain_text(children: list[Token], first_line: bool = False) -> str:
    """The text of inline tokens, without the marks; a line break is one."""

    parts: list[str] = []
    for child in children:
        if child.type in ("softbreak", "hardbreak"):
            if first_line:
                break
            parts.append("\n")
        elif child.type == "image" and child.children:
            parts.append(plain_text(child.children))
        elif child.type in ("text", "code_inline", "image"):
            parts.append(child.content)
    return "".join(parts)


def first_line(text: str) -> str:
    """
    The first line of a README as plain text, for a list of projects.

    It's the first line of the first block that has text: a heading without
    its ``#``, a paragraph without its marks, the first line of a code block.
    """

    for token in parse(text):
        if token.type == "inline" and token.children:
            line = plain_text(token.children, first_line=True).strip()
        elif token.type == "fence":
            line = token.content.split("\n", 1)[0].strip()
        else:
            continue
        if line:
            return line
    return ""


def picture_path(src: str) -> str | None:
    """
    The path of a picture in the folder of the project, as the parser wrote
    it, a URL with %XX for some characters: None for a URL with a scheme or
    a host, an absolute path or nothing. A ? or a # ends it.
    """

    parts = urlsplit(src)
    if parts.scheme or parts.netloc or parts.path.startswith("/"):
        return None
    return unquote(parts.path) or None


def first_paragraph(text: str) -> str:
    """
    The Markdown of the first paragraph of a README that isn't a heading.

    Only a paragraph at the top: not one in a list or in a quote. Return ""
    if there is none.
    """

    # the lines as the parser counts them
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for token in parse(text):
        if token.type == "paragraph_open" and token.level == 0 and token.map:
            start, end = token.map
            return "\n".join(lines[start:end]).strip()
    return ""
