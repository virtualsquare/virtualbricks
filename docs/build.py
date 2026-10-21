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
Build the documentation from its Markdown sources with pandoc.

    docs/guide/<page>.md            the user guide, pandoc's Markdown
    docs/guide/figures/             its pictures, which the end-to-end tests
                                    take: pytest --pictures -m pictures
    docs/man/<page>.<section>.md    the man pages, pandoc's Markdown
    docs/built/man/                 the man pages
    docs/built/mallard/             the guide in Mallard, for Yelp, with a
                                    copy of its pictures in figures/, and a
                                    page for each man page, its Reference

The outputs are committed like the catalogs, and written only by this script.
docs/README.md says how a page is written.

VERSION and DATE in the metadata of a man page become the version of
Virtualbricks and the date of the page. The date changes only when the page
does, or comes from SOURCE_DATE_EPOCH: running the script twice in a row leaves
the tree untouched. With --check it writes nothing and exits with 1 if an
output is out of date.

It uses the pandoc of the pypandoc-binary package if it's installed, as in the
pre-commit hook and the dev dependency group, so that everyone builds with the
same version, or else the pandoc on the PATH.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import string
import subprocess
import sys
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUIDE = os.path.join(HERE, "guide")
TEMPLATES = os.path.join(HERE, "templates")
MAN = os.path.join(HERE, "man")
BUILT = os.path.join(HERE, "built")
MAN_SOURCE = re.compile(r"^(?P<page>.+)\.(?P<section>[1-9])\.md$")
FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
# The title line of a man page, with the date; see today() and body().
TITLE = re.compile(r"^\.TH .*$", re.MULTILINE)
# "--" must stay two hyphens in options such as --in-place, and "[settings]"
# must not become a link to the SETTINGS section
MARKDOWN = "markdown-smart-implicit_header_references"
# A section of the guide has the id that links name, written by hand, never
# made from its title
GUIDE_MARKDOWN = MARKDOWN + "-auto_identifiers"
MALLARD_NS = "http://projectmallard.org/1.0/"
# The keys of the front matter of a page of the guide
GUIDE_META = {"type", "guide", "seealso", "sort", "desc", "title-text"}
# Those of a man page: pandoc's, then those of its page in the guide
REFERENCE_META = {"title", "section", "header", "footer", "date"} | {
    "help",
    "guide",
    "sort",
}
# The words that keep their capitals in a heading of a man page, which is in
# capitals there and in sentence case in the guide
CAPITALS = {
    "amp": "AMP",
    "json": "JSON",
    "readme": "README",
    "toml": "TOML",
    "virtualbricks": "Virtualbricks",
}
MIME = {".png": "image/png", ".svg": "image/svg+xml"}
# A label of a menu, then the next one: Projects › Import…
MENU_STEP = " › "


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


def pandoc(path, args, text, source):
    result = subprocess.run(
        [path, *args],
        input=text,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise Error(f"{source}: {result.stderr.strip()}")
    return result.stdout


def read(path):
    with open(path, encoding="utf-8") as fp:
        return fp.read()


def version():
    text = read(os.path.join(ROOT, "virtualbricks", "__init__.py"))
    match = re.search(r"^__version__ = ['\"](.*)['\"]$", text, re.M)
    return match.group(1)


def today():
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        moment = datetime.datetime.fromtimestamp(
            int(epoch), datetime.timezone.utc
        )
        return moment.date().isoformat()
    return datetime.date.today().isoformat()


# The man pages


def man_page(pandoc_bin, source, date):
    text = read(source)
    match = FRONT_MATTER.match(text)
    if match is None:
        raise Error(f"{source}: no metadata block at the top")
    metadata = match.group(0).replace("VERSION", version())
    text = metadata.replace("DATE", date) + text[match.end() :]
    return pandoc(
        pandoc_bin,
        ["--standalone", f"--from={MARKDOWN}", "--to=man"],
        text,
        source,
    )


def body(page):
    """A man page without its title line, which holds the date."""

    return TITLE.sub("", page, count=1)


def unchanged_man(current, page):
    """True if the man page current needs no rewrite to become page."""

    if body(current) != body(page):
        return False
    return "SOURCE_DATE_EPOCH" not in os.environ or current == page


# The guide in Mallard


def text(inlines):
    """The plain text of pandoc inlines."""

    parts = []
    for inline in inlines:
        kind = inline["t"]
        if kind == "Str":
            parts.append(inline["c"])
        elif kind in ("Space", "SoftBreak"):
            parts.append(" ")
        elif kind in ("Strong", "Emph"):
            parts.append(text(inline["c"]))
        elif kind == "Code":
            parts.append(inline["c"][1])
        elif kind == "Span":
            parts.append(text(inline["c"][1]))
        else:
            raise Error(f"{kind} where only text can be")
    return "".join(parts)


def words(value):
    """The pandoc inlines of a plain text, as a title given as attribute."""

    result = []
    for index, word in enumerate(value.split()):
        if index:
            result.append({"t": "Space"})
        result.append({"t": "Str", "c": word})
    return result


def meta_text(value):
    """The text of a value of the front matter."""

    kind = value["t"]
    if kind == "MetaString":
        return value["c"]
    if kind == "MetaInlines":
        return text(value["c"])
    if kind == "MetaBlocks" and len(value["c"]) == 1:
        return text(value["c"][0]["c"])
    raise Error(f"a {kind} where a text should be")


def meta_list(value):
    if value["t"] == "MetaList":
        return [meta_text(item) for item in value["c"]]
    return [meta_text(value)]


def keys(sequence):
    """The keys of Ctrl+Q; of Ctrl++, Ctrl and the key +."""

    if sequence.endswith("++"):
        result = sequence[:-2].split("+") + ["+"]
    else:
        result = sequence.split("+")
    if "" in result:
        raise Error(f"a key sequence with an empty key: {sequence}")
    return result


def sentence_case(title):
    """A heading in capitals, COMMON RULES, as Common rules."""

    result = []
    for index, word in enumerate(title.split(" ")):
        word = CAPITALS.get(word.lower(), word.lower())
        if index == 0:
            word = word[:1].upper() + word[1:]
        result.append(word)
    return " ".join(result)


class Element:
    """An element of Mallard, as the writer makes it."""

    def __init__(self, tag, attrs=None, children=None, inline=False):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = children if children is not None else []
        # its children on its own line, as those of a paragraph
        self.inline = inline

    def start(self):
        attrs = "".join(
            f" {name}={quoteattr(value)}" for name, value in self.attrs.items()
        )
        return f"<{self.tag}{attrs}"

    def inline_xml(self):
        if not self.children:
            return self.start() + "/>"
        content = "".join(
            escape(child) if isinstance(child, str) else child.inline_xml()
            for child in self.children
        )
        return f"{self.start()}>{content}</{self.tag}>"

    def lines(self, indent=""):
        if self.inline or not self.children:
            yield indent + self.inline_xml()
            return
        if self.tag == "screen":
            yield f"{indent}{self.start()}>{escape(self.children[0])}</screen>"
            return
        yield f"{indent}{self.start()}>"
        for child in self.children:
            yield from child.lines(indent + "  ")
        yield f"{indent}</{self.tag}>"


def append(result, item):
    """Add text or an element to mixed content, joining texts."""

    if isinstance(item, str) and result and isinstance(result[-1], str):
        result[-1] += item
    else:
        result.append(item)


class MallardWriter:
    """
    A page of the guide, from pandoc's tree of its Markdown: the marks of
    docs/README.md become the elements of Mallard. Anything else is an
    error: the writer never drops a part of a page.
    """

    # the pages, in the errors
    WHERE = "the guide"

    def __init__(self, name, document):
        self.name = name
        self.document = document

    def para(self, tag, inlines, attrs=None):
        """An element of text and marks, as a paragraph or a title."""

        return Element(tag, attrs, self.inlines(inlines), inline=True)

    # Inlines

    def inlines(self, inlines):
        """Text and elements, the spaces collapsed."""

        result = []
        for inline in inlines:
            for item in self.inline(inline):
                append(result, item)
        return result

    def inline(self, inline):
        kind = inline["t"]
        content = inline.get("c")
        if kind == "Str":
            return [content]
        if kind in ("Space", "SoftBreak"):
            return [" "]
        if kind == "Emph":
            return [Element("var", children=self.inlines(content))]
        if kind == "Link":
            _attr, linked, (target, _title) = content
            attr = (
                "href" if re.match(r"^[a-z][a-z0-9+.-]*:", target) else "xref"
            )
            return [Element("link", {attr: target}, self.inlines(linked))]
        return self.mark(kind, content)

    def mark(self, kind, content):
        """The marks of the guide: labels, commands, keys."""

        if kind == "Strong":
            label = text(content)
            if MENU_STEP in label:
                return [
                    Element(
                        "guiseq",
                        children=[
                            Element("gui", children=[part])
                            for part in label.split(MENU_STEP)
                        ],
                    )
                ]
            return [Element("gui", children=[label])]
        if kind == "Code":
            (_id, classes, _attrs), code = content
            if classes == []:
                return [Element("code", children=[code])]
            if classes in (["cmd"], ["sys"], ["file"]):
                return [Element(classes[0], children=[code])]
            raise Error(f"code of class {' '.join(classes)}: {code}")
        if kind == "Span":
            (_id, classes, _attrs), spanned = content
            if classes == ["key"]:
                return [Element("key", children=[text(spanned)])]
            if classes == ["keyseq"]:
                return [
                    Element(
                        "keyseq",
                        children=[
                            Element("key", children=[key])
                            for key in keys(text(spanned))
                        ],
                    )
                ]
            if classes in (["app"], ["cmd"]):
                return [Element(classes[0], children=self.inlines(spanned))]
            raise Error(
                f"a span of class {' '.join(classes)}: {text(spanned)}"
            )
        raise Error(f"{kind}, which {self.WHERE} doesn't use")

    # Blocks

    def blocks(self, blocks):
        result = []
        for block in blocks:
            result.extend(self.block(block))
        return result

    def block(self, block):
        kind = block["t"]
        content = block.get("c")
        if kind in ("Para", "Plain"):
            return [self.para("p", content)]
        if kind == "BulletList":
            return [Element("list", children=self.items(content))]
        if kind == "OrderedList":
            return [self.numbered(self.items(content[1]))]
        if kind == "DefinitionList":
            return [Element("terms", children=self.terms(content))]
        if kind == "CodeBlock":
            (_id, classes, _attrs), code = content
            if classes:
                raise Error(f"a code block of class {' '.join(classes)}")
            return [Element("screen", children=[code])]
        if kind == "Figure":
            return [self.figure(content)]
        if kind == "Table":
            return [self.table(content)]
        if kind == "Div":
            return self.div(content)
        raise Error(f"{kind}, which {self.WHERE} doesn't use")

    def numbered(self, items):
        """A numbered list of the guide: a procedure."""

        return Element("steps", children=items)

    def items(self, items):
        return [
            Element("item", children=self.blocks(blocks)) for blocks in items
        ]

    def terms(self, items):
        result = []
        for term, definitions in items:
            children = [self.para("title", term)]
            for definition in definitions:
                children.extend(self.blocks(definition))
            result.append(Element("item", children=children))
        return result

    def figure(self, content):
        _attr, (_short, caption), blocks = content
        if len(caption) != 1 or len(blocks) != 1 or len(blocks[0]["c"]) != 1:
            raise Error("a figure is a picture alone, with its caption")
        image = blocks[0]["c"][0]
        if image["t"] != "Image":
            raise Error("a figure is a picture alone, with its caption")
        _attr, alt, (src, _title) = image["c"]
        mime = MIME.get(os.path.splitext(src)[1])
        if mime is None:
            raise Error(f"a picture of an unknown type: {src}")
        # without alt="…", pandoc gives the picture its caption as its text
        if not alt or text(alt) == text(caption[0]["c"]):
            raise Error(f"the picture {src} has no alt text")
        media = Element(
            "media",
            {"type": "image", "mime": mime, "src": src},
            [self.para("p", alt)],
        )
        return Element(
            "figure", children=[self.para("title", caption[0]["c"]), media]
        )

    def table(self, content):
        _attr, _caption, _specs, head, bodies, _foot = content
        rows = [("thead", head[1])] + [("tbody", b[3]) for b in bodies]
        children = []
        for tag, body_rows in rows:
            if not body_rows:
                continue
            trs = []
            for _row_attr, cells in body_rows:
                tds = [
                    Element("td", children=self.blocks(cell[4]))
                    for cell in cells
                ]
                trs.append(Element("tr", children=tds))
            children.append(Element(tag, children=trs))
        return Element("table", {"frame": "all", "rules": "rows"}, children)

    def div(self, content):
        (_id, classes, attrs), blocks = content
        attrs = dict(attrs)
        if classes == ["terms"] and set(attrs) == {"title"}:
            inner = self.blocks(blocks)
            if len(inner) != 1 or inner[0].tag != "terms":
                raise Error("a div of class terms holds a list of terms")
            title = self.para("title", words(attrs["title"]))
            inner[0].children.insert(0, title)
            return inner
        if classes[:1] == ["note"] and not attrs and len(classes) <= 2:
            note = Element("note", children=self.blocks(blocks))
            if len(classes) == 2:
                note.attrs["style"] = classes[1]
            return [note]
        raise Error(f"a div of class {' '.join(classes)} {attrs}")

    # The page

    def info(self, meta):
        unknown = set(meta) - GUIDE_META
        if unknown:
            raise Error(f"unknown keys in the front matter: {sorted(unknown)}")
        children = self.guide_links(meta)
        for xref in meta_list(meta["seealso"]) if "seealso" in meta else []:
            children.append(Element("link", {"type": "seealso", "xref": xref}))
        if "title-text" in meta:
            children.append(
                Element(
                    "title",
                    {"type": "text"},
                    [meta_text(meta["title-text"])],
                    inline=True,
                )
            )
        children.extend(self.sort_title(meta))
        if "desc" in meta:
            value = meta["desc"]
            if value["t"] == "MetaInlines":
                inlines = value["c"]
            else:
                inlines = words(meta_text(value))
            children.append(self.para("desc", inlines))
        return Element("info", children=children)

    @staticmethod
    def guide_links(meta):
        return [
            Element("link", {"type": "guide", "xref": xref})
            for xref in (meta_list(meta["guide"]) if "guide" in meta else [])
        ]

    @staticmethod
    def sort_title(meta):
        if "sort" not in meta:
            return []
        sort = meta_text(meta["sort"])
        return [Element("title", {"type": "sort"}, [sort], inline=True)]

    def page(self):
        meta = self.document["meta"]
        blocks = self.document["blocks"]
        if not blocks or blocks[0]["t"] != "Header" or blocks[0]["c"][0] != 1:
            raise Error("a page starts with its title, # Title")
        kind = meta_text(meta["type"]) if "type" in meta else "topic"
        if kind not in ("topic", "guide"):
            raise Error(f"a page of type {kind}")
        children = [self.info(meta), self.para("title", blocks[0]["c"][2])]
        section = None
        for block in blocks[1:]:
            if block["t"] == "Header":
                level, (ident, classes, attrs), title = block["c"]
                if level != 2:
                    raise Error(f"a heading of level {level}: {text(title)}")
                if not ident:
                    raise Error(
                        f"the section {text(title)} has no id: {{#id}}"
                    )
                if classes or set(dict(attrs)) - {"style"}:
                    raise Error(
                        f"the heading {text(title)} has {classes} {attrs}"
                    )
                section = Element("section", {"id": ident, **dict(attrs)})
                section.children.append(self.para("title", title))
                children.append(section)
            else:
                target = children if section is None else section.children
                target.extend(self.block(block))
        return self.xml(kind, children)

    def xml(self, kind, children):
        attrs = {"xmlns": MALLARD_NS, "type": kind, "id": self.name}
        root = Element("page", attrs, children)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            + "\n".join(root.lines())
            + "\n"
        )


def cross_reference(references, own, inline, following):
    """
    **name**(5), a man page of the reference that isn't the page's own: the
    id of its page, the name with its section, and the rest of the text.
    """

    if inline["t"] != "Strong" or following is None:
        return None
    if following["t"] != "Str":
        return None
    name = text(inline["c"])
    if name not in references:
        return None
    section, page = references[name]
    mark = f"({section})"
    if page == own or not following["c"].startswith(mark):
        return None
    return page, name + mark, following["c"][len(mark) :]


def heading_text(inlines, attrs):
    """The title of a section of a man page, as plain text."""

    if "title" in attrs:
        return attrs["title"]
    heading = text(inlines)
    if heading == heading.upper():
        return sentence_case(heading)
    return heading


class ReferenceWriter(MallardWriter):
    """
    A page of the reference, from pandoc's tree of a man page: bold is
    literal text, italics a part to replace; NAME is the description of the
    page and SYNOPSIS a synopsis; a heading in capitals is in sentence case;
    a man page of the reference, as **virtualbricks-config**(5), is a link
    to its page.
    """

    WHERE = "the reference"

    def __init__(self, name, document, references):
        super().__init__(name, document)
        # the pages of the reference by the names of their man pages, as
        # {"virtualbricks-config": ("5", "config-files")}
        self.references = references

    def inlines(self, inlines):
        result = []
        index = 0
        while index < len(inlines):
            inline = inlines[index]
            following = (
                inlines[index + 1] if index + 1 < len(inlines) else None
            )
            link = self.cross_reference(inline, following)
            if link is None:
                items = self.inline(inline)
                index += 1
            else:
                items = link
                index += 2
            for item in items:
                append(result, item)
        return result

    def cross_reference(self, inline, following):
        found = cross_reference(self.references, self.name, inline, following)
        if found is None:
            return None
        page, label, rest = found
        link = Element("link", {"xref": page}, [label])
        return [link, rest] if rest else [link]

    def mark(self, kind, content):
        """The marks of a man page: literal text, as typed."""

        if kind == "Strong":
            return [Element("code", children=self.inlines(content))]
        if kind == "Code":
            (_id, classes, _attrs), code = content
            if classes:
                raise Error(f"code of class {' '.join(classes)}: {code}")
            return [Element("code", children=[code])]
        if kind == "LineBreak":
            raise Error("a line break, which only the synopsis has")
        raise Error(f"{kind}, which {self.WHERE} doesn't use")

    def numbered(self, items):
        """A numbered list of the reference, not a procedure."""

        return Element("list", {"type": "numbered"}, items)

    def synopsis(self, block):
        """The lines of the synopsis: a paragraph for each."""

        if block["t"] != "Para":
            raise Error(f"a {block['t']} in the synopsis")
        lines = [[]]
        for inline in block["c"]:
            if inline["t"] == "LineBreak":
                lines.append([])
            else:
                lines[-1].append(inline)
        return [self.para("p", line) for line in lines]

    def description(self, blocks):
        """
        The description of the page, from NAME, "name - what it is": the
        name of the man page, then what it is.
        """

        if len(blocks) != 1 or blocks[0]["t"] != "Para":
            raise Error("NAME is a paragraph, name - what it is")
        inlines = blocks[0]["c"]
        dash = {"t": "Str", "c": "-"}
        if dash not in inlines:
            raise Error("NAME is a paragraph, name - what it is")
        index = inlines.index(dash)
        name = text(inlines[:index]).strip()
        what = inlines[index + 1 :]
        while what and what[0]["t"] in ("Space", "SoftBreak"):
            what = what[1:]
        section = meta_text(self.document["meta"]["section"])
        children = [f"{name}({section}): "]
        for item in self.inlines(what):
            append(children, item)
        return Element("desc", children=children, inline=True)

    def heading(self, inlines, attrs):
        """The title of a section."""

        if "title" in attrs:
            return self.para("title", words(attrs["title"]))
        heading = text(inlines)
        if heading == heading.upper():
            return Element(
                "title", children=[sentence_case(heading)], inline=True
            )
        return self.para("title", inlines)

    def page(self):
        meta = self.document["meta"]
        unknown = set(meta) - REFERENCE_META
        if unknown:
            raise Error(f"unknown keys in the front matter: {sorted(unknown)}")
        info = Element("info", children=self.guide_links(meta))
        info.children.extend(self.sort_title(meta))
        title = meta_text(meta["help"]["c"]["title"])
        children = [
            info,
            Element("title", children=[title], inline=True),
            Element("links", {"type": "section"}),
        ]
        # the sections open at each level: (level, their children)
        open_sections = [(0, children)]
        # the blocks of NAME, while they come, and once they came
        name = None
        name_blocks = None
        synopsis = None
        for block in self.document["blocks"]:
            if block["t"] != "Header":
                if name is not None:
                    name.append(block)
                elif synopsis is not None:
                    synopsis.children.extend(self.synopsis(block))
                else:
                    open_sections[-1][1].extend(self.block(block))
                continue
            level, (ident, classes, attrs), inlines = block["c"]
            attrs = dict(attrs)
            heading = text(inlines)
            if classes or set(attrs) - {"title"}:
                raise Error(f"the heading {heading} has {classes} {attrs}")
            while open_sections[-1][0] >= level:
                open_sections.pop()
            if open_sections[-1][0] != level - 1 or level > 3:
                raise Error(f"a heading of level {level} there: {heading}")
            name = [] if (level, heading) == (1, "NAME") else None
            synopsis = None
            if name is not None:
                name_blocks = name
                continue
            section = Element("section", {"id": ident})
            section.children.append(self.heading(inlines, attrs))
            if (level, heading) == (1, "SYNOPSIS"):
                synopsis = Element("synopsis")
                section.children.append(synopsis)
            open_sections[-1][1].append(section)
            open_sections.append((level, section.children))
        if name_blocks is None:
            raise Error("a man page has its NAME")
        info.children.append(self.description(name_blocks))
        return self.xml("topic", children)


def tree(pandoc_bin, source, markdown):
    """pandoc's tree of a page."""

    return json.loads(
        pandoc(
            pandoc_bin,
            ["--standalone", f"--from={markdown}", "--to=json"],
            read(source),
            source,
        )
    )


def written(writer, source):
    try:
        return writer.page()
    except Error as exc:
        raise Error(f"{source}: {exc}") from None


def mallard_page(pandoc_bin, source):
    """A page of the guide, in Mallard."""

    name = os.path.basename(source)[: -len(".md")]
    document = tree(pandoc_bin, source, GUIDE_MARKDOWN)
    return written(MallardWriter(name, document), source)


def reference_id(document, source):
    """The id of the page of a man page: the id of help in its front matter."""

    value = document["meta"].get("help")
    if value is None or value["t"] != "MetaMap":
        raise Error(f"{source}: no help: {{id: …, title: …}}")
    if set(value["c"]) != {"id", "title"}:
        raise Error(f"{source}: help has an id and a title, and only those")
    return meta_text(value["c"]["id"])


# The HTML


def raw(html):
    return {"t": "RawInline", "c": ["html", html]}


def link(inlines, href):
    return {"t": "Link", "c": [["", [], []], inlines, [href, ""]]}


def div(classes, blocks, attrs=()):
    return {"t": "Div", "c": [["", classes, list(attrs)], blocks]}


def para(inlines):
    return {"t": "Para", "c": inlines}


class Page:
    """What a page tells the others: its title, its sections, its place."""

    def __init__(self, name, title, desc, guides, seealso, sort, sections):
        self.name = name
        # plain text
        self.title = title
        # pandoc inlines, as the page's writer makes them HTML
        self.desc = desc
        # its sections of the index, as index#lab
        self.guides = guides
        self.seealso = seealso
        self.sort = sort
        # {id: title} of its sections
        self.sections = sections


class Site:
    """The pages of the HTML, which link each other."""

    def __init__(self):
        self.pages = {}

    def add(self, page):
        self.pages[page.name] = page

    def resolve(self, target):
        """The file and the title of the page, or section, of a link."""

        name, _, section = target.partition("#")
        page = self.pages.get(name)
        if page is None:
            raise Error(f"a link to a page that isn't there: {target}")
        if not section:
            return f"{name}.html", page.title
        if section not in page.sections:
            raise Error(f"a link to a section that isn't there: {target}")
        return f"{name}.html#{section}", page.sections[section]

    def listed(self, section):
        """The pages of a section of the index, index#lab, in order."""

        pages = [p for p in self.pages.values() if section in p.guides]
        pages.sort(key=lambda p: (p.sort, p.title))
        return [(f"{p.name}.html", p.title, p.desc) for p in pages]

    def see_also(self, name):
        """
        The pages, or sections, that a page names in See also, and the pages
        that name it or one of its sections.
        """

        items = {}
        for target in self.pages[name].seealso:
            href, title = self.resolve(target)
            page, _, section = target.partition("#")
            items[href] = (title, [] if section else self.pages[page].desc)
        for page in self.pages.values():
            names = {target.partition("#")[0] for target in page.seealso}
            if page.name != name and name in names:
                items.setdefault(f"{page.name}.html", (page.title, page.desc))
        return sorted(
            ((href, title, desc) for href, (title, desc) in items.items()),
            key=lambda item: item[1],
        )

    @staticmethod
    def links(items):
        """Pages, or sections, each with its line, as the index has them."""

        return div(
            ["links"],
            [
                div(
                    ["link"],
                    [para([link(words(title), href)])]
                    + ([div(["desc"], [para(desc)])] if desc else []),
                )
                for href, title, desc in items
            ],
        )

    def trail(self, page):
        """The way back to the sections of the index that list a page."""

        lines = []
        for guide in page.guides:
            index, _, section = guide.partition("#")
            href, title = self.resolve(guide)
            first = link(words(self.pages[index].title), f"{index}.html")
            line = [first]
            if section:
                line += [{"t": "Space"}, {"t": "Str", "c": "›"}]
                line += [{"t": "Space"}, link(words(title), href)]
            lines.append(para(line))
        return [div(["trail"], lines)] if lines else []


class HtmlWriter:
    """
    A page of the guide in HTML: pandoc's tree, with the marks of the guide
    made HTML and its links links between the files, and what Yelp adds to
    a page: the way back to the index, See also, the lists of the index.
    """

    KIND = "guide"

    def __init__(self, name, document, site):
        self.name = name
        self.document = document
        self.site = site

    # Inlines

    def inlines(self, inlines):
        return [item for inline in inlines for item in self.inline(inline)]

    def inline(self, inline):
        kind = inline["t"]
        content = inline.get("c")
        if kind in ("Str", "Space", "SoftBreak"):
            return [inline]
        if kind == "Emph":
            return [{"t": "Emph", "c": self.inlines(content)}]
        if kind == "Link":
            attr, linked, (target, title) = content
            if re.match(r"^[a-z][a-z0-9+.-]*:", target):
                return [
                    {
                        "t": "Link",
                        "c": [attr, self.inlines(linked), [target, title]],
                    }
                ]
            href, label = self.site.resolve(target)
            return [link(self.inlines(linked) or words(label), href)]
        return self.mark(kind, content)

    def mark(self, kind, content):
        if kind == "Strong":
            label = text(content)
            if MENU_STEP not in label:
                return [{"t": "Span", "c": [["", ["gui"], []], words(label)]}]
            parts = []
            for part in label.split(MENU_STEP):
                if parts:
                    parts += [{"t": "Space"}, {"t": "Str", "c": "›"}]
                    parts += [{"t": "Space"}]
                parts.append(
                    {"t": "Span", "c": [["", ["gui"], []], words(part)]}
                )
            return [{"t": "Span", "c": [["", ["guiseq"], []], parts]}]
        if kind == "Code":
            return [{"t": "Code", "c": content}]
        if kind == "Span":
            (_id, classes, _attrs), spanned = content
            if classes == ["key"]:
                return [raw(f"<kbd>{escape(text(spanned))}</kbd>")]
            if classes == ["keyseq"]:
                return [
                    raw(
                        "+".join(
                            f"<kbd>{escape(key)}</kbd>"
                            for key in keys(text(spanned))
                        )
                    )
                ]
            return [
                {"t": "Span", "c": [["", classes, []], self.inlines(spanned)]}
            ]
        raise Error(f"{kind}, which the HTML doesn't write")

    # Blocks

    def blocks(self, blocks):
        return [item for block in blocks for item in self.block(block)]

    def block(self, block):
        kind = block["t"]
        content = block.get("c")
        if kind in ("Para", "Plain"):
            return [{"t": kind, "c": self.inlines(content)}]
        if kind == "BulletList":
            return [{"t": kind, "c": [self.blocks(item) for item in content]}]
        if kind == "OrderedList":
            items = [self.blocks(item) for item in content[1]]
            return [{"t": kind, "c": [content[0], items]}]
        if kind == "DefinitionList":
            items = [
                [self.inlines(term), [self.blocks(d) for d in definitions]]
                for term, definitions in content
            ]
            return [{"t": kind, "c": items}]
        if kind == "CodeBlock":
            return [block]
        if kind == "Figure":
            attr, (short, caption), (picture,) = content
            image = picture["c"][0]
            src = image["c"][2][0]
            image = {
                "t": "Image",
                "c": [
                    image["c"][0],
                    self.inlines(image["c"][1]),
                    image["c"][2],
                ],
            }
            caption = [{"t": "Plain", "c": self.inlines(caption[0]["c"])}]
            return [
                {
                    "t": "Figure",
                    "c": [
                        attr,
                        [short, caption],
                        [{"t": "Plain", "c": [link([image], src)]}],
                    ],
                }
            ]
        if kind == "Table":
            return [self.table(content)]
        if kind == "Div":
            (ident, classes, attrs), inner = content
            attrs = dict(attrs)
            inner = self.blocks(inner)
            if "title" in attrs:
                title = escape(attrs.pop("title"))
                inner.insert(
                    0,
                    {
                        "t": "RawBlock",
                        "c": ["html", f'<p class="title">{title}</p>'],
                    },
                )
            return [div(classes, inner, attrs.items())]
        raise Error(f"{kind}, which the HTML doesn't write")

    def table(self, content):
        attr, caption, specs, head, bodies, foot = content

        def rows(rows):
            return [
                [
                    row_attr,
                    [cell[:4] + [self.blocks(cell[4])] for cell in cells],
                ]
                for row_attr, cells in rows
            ]

        head = [head[0], rows(head[1])]
        bodies = [[b[0], b[1], rows(b[2]), rows(b[3])] for b in bodies]
        foot = [foot[0], rows(foot[1])]
        return {"t": "Table", "c": [attr, caption, specs, head, bodies, foot]}

    # The page

    def page_info(self):
        """What the page tells the others."""

        meta = self.document["meta"]
        title = self.document["blocks"][0]["c"][2]
        if "title-text" in meta:
            title = meta_text(meta["title-text"])
        else:
            title = text(title)
        desc = []
        if "desc" in meta:
            value = meta["desc"]
            if value["t"] == "MetaInlines":
                desc = value["c"]
            else:
                desc = words(meta_text(value))
        sections = {}
        for block in self.document["blocks"][1:]:
            if block["t"] == "Header":
                sections[block["c"][1][0]] = text(block["c"][2])
        return Page(
            self.name,
            title,
            desc,
            meta_list(meta["guide"]) if "guide" in meta else [],
            meta_list(meta["seealso"]) if "seealso" in meta else [],
            meta_text(meta["sort"]) if "sort" in meta else title,
            sections,
        )

    def body(self):
        """The blocks of the page, and the contents beside them."""

        page = self.site.pages[self.name]
        blocks = self.document["blocks"]
        body = self.site.trail(page)
        body.append(
            {
                "t": "Header",
                "c": [1, ["", [], []], self.inlines(blocks[0]["c"][2])],
            }
        )
        for block in blocks[1:]:
            if block["t"] != "Header":
                body.extend(self.block(block))
                continue
            level, (ident, _classes, attrs), title = block["c"]
            classes = (
                ["columns"] if dict(attrs).get("style") == "2column" else []
            )
            body.append(
                {
                    "t": "Header",
                    "c": [level, [ident, classes, []], self.inlines(title)],
                }
            )
            listed = self.site.listed(f"{self.name}#{ident}")
            if listed:
                body.append(self.site.links(listed))
        see_also = self.site.see_also(self.name)
        if see_also:
            body.append(
                div(
                    ["seealso"],
                    [
                        {
                            "t": "Header",
                            "c": [2, ["seealso", [], []], words("See also")],
                        },
                        self.site.links(see_also),
                    ],
                )
            )
        return body, ""


class ReferenceHtml(HtmlWriter):
    """
    A man page in HTML, as it is in the guide: NAME under its title, the
    contents of its sections beside it.
    """

    KIND = "reference"

    def __init__(self, name, document, site, references):
        super().__init__(name, document, site)
        self.references = references

    def inlines(self, inlines):
        result = []
        index = 0
        while index < len(inlines):
            following = (
                inlines[index + 1] if index + 1 < len(inlines) else None
            )
            found = cross_reference(
                self.references, self.name, inlines[index], following
            )
            run = self.literal_run(inlines, index)
            if found is None and len(run) > 1:
                result.extend(self.literal(run))
                index += len(run)
                continue
            if found is None:
                result.extend(self.inline(inlines[index]))
                index += 1
                continue
            page, label, rest = found
            result.append(link(words(label), f"{page}.html"))
            if rest:
                result.append({"t": "Str", "c": rest})
            index += 2
        return result

    @staticmethod
    def literal_run(inlines, index):
        """Bold and italics side by side, without a space: one literal."""

        run = []
        while index < len(inlines) and inlines[index]["t"] in (
            "Strong",
            "Emph",
        ):
            run.append(inlines[index])
            index += 1
        return run if any(i["t"] == "Strong" for i in run) else run[:1]

    def literal(self, run):
        """**unix:***path*: one code, its part to replace inside."""

        result = [raw("<code>")]
        for inline in run:
            if inline["t"] == "Strong":
                result.extend(self.inlines(inline["c"]))
            else:
                result.append({"t": "Emph", "c": self.inlines(inline["c"])})
        return result + [raw("</code>")]

    def mark(self, kind, content):
        if kind == "Strong":
            return self.literal([{"t": "Strong", "c": content}])
        if kind == "Code":
            return [{"t": "Code", "c": content}]
        if kind == "LineBreak":
            return [{"t": "LineBreak"}]
        raise Error(f"{kind}, which the HTML doesn't write")

    def heading(self, inlines, attrs):
        if "title" in attrs:
            return words(attrs["title"])
        heading = text(inlines)
        if heading == heading.upper():
            return words(sentence_case(heading))
        return self.inlines(inlines)

    def name_line(self):
        """NAME: the name of the man page, and what it is."""

        blocks = self.document["blocks"]
        start = blocks.index(
            next(
                b
                for b in blocks
                if b["t"] == "Header" and text(b["c"][2]) == "NAME"
            )
        )
        inlines = blocks[start + 1]["c"]
        index = inlines.index({"t": "Str", "c": "-"})
        name = text(inlines[:index]).strip()
        what = inlines[index + 1 :]
        while what and what[0]["t"] in ("Space", "SoftBreak"):
            what = what[1:]
        return name, what

    def page_info(self):
        meta = self.document["meta"]
        name, what = self.name_line()
        section = meta_text(meta["section"])
        sections = {}
        for block in self.document["blocks"]:
            if block["t"] == "Header" and text(block["c"][2]) != "NAME":
                attrs = dict(block["c"][1][2])
                sections[block["c"][1][0]] = heading_text(block["c"][2], attrs)
        return Page(
            self.name,
            meta_text(meta["help"]["c"]["title"]),
            [{"t": "Str", "c": f"{name}({section}):"}, {"t": "Space"}] + what,
            meta_list(meta["guide"]) if "guide" in meta else [],
            [],
            meta_text(meta["sort"]) if "sort" in meta else "",
            sections,
        )

    def body(self):
        page = self.site.pages[self.name]
        meta = self.document["meta"]
        name, what = self.name_line()
        section = meta_text(meta["section"])
        body = self.site.trail(page)
        body.append({"t": "Header", "c": [1, ["", [], []], words(page.title)]})
        body.append(div(["lede"], [{"t": "Para", "c": self.inlines(what)}]))
        body.append(
            div(
                ["meta"],
                [
                    para(
                        words(f"{name}({section}) · Virtualbricks {version()}")
                    )
                ],
            )
        )
        contents = []
        skip = False
        synopsis = None
        for block in self.document["blocks"]:
            if block["t"] != "Header":
                if skip:
                    continue
                if synopsis is not None:
                    synopsis["c"][1].extend(self.block(block))
                else:
                    body.extend(self.block(block))
                continue
            level, (ident, _classes, attrs), inlines = block["c"]
            heading = text(inlines)
            skip = (level, heading) == (1, "NAME")
            synopsis = None
            if skip:
                continue
            title = self.heading(inlines, dict(attrs))
            body.append(
                {"t": "Header", "c": [level + 1, [ident, [], []], title]}
            )
            if level == 1:
                contents.append((ident, heading_text(inlines, dict(attrs))))
            if (level, heading) == (1, "SYNOPSIS"):
                synopsis = div(["synopsis"], [])
                body.append(synopsis)
        toc = "".join(
            f'<li><a href="#{escape(ident)}">{escape(title)}</a></li>\n'
            for ident, title in contents
        )
        nav = (
            '<nav class="toc" aria-label="Contents">\n'
            '<p class="toc-label">Contents</p>\n'
            f"<ol>\n{toc}</ol>\n</nav>\n"
        )
        return body, nav


def html_page(pandoc_bin, writer, api):
    """The HTML of a page, in the template."""

    body, contents = writer.body()
    document = {"pandoc-api-version": api, "meta": {}, "blocks": body}
    html = pandoc(
        pandoc_bin,
        # no colours of a language: the class of a code is a mark of the
        # guide, as cmd, which pandoc would take for Windows batch files
        ["--from=json", "--to=html5", "--syntax-highlighting=none"],
        json.dumps(document),
        writer.name,
    )
    page = writer.site.pages[writer.name]
    index = writer.site.pages.get("index")
    title = page.title
    if index is not None and page is not index:
        title += f" — {index.title}"
    with open(os.path.join(TEMPLATES, "page.html"), encoding="utf-8") as fp:
        template = string.Template(fp.read())
    return template.substitute(
        title=escape(title), kind=writer.KIND, contents=contents, body=html
    )


# The outputs


def outputs(pandoc_bin, date):
    """
    Every output, as {path relative to BUILT: (content, unchanged)}, where
    unchanged(current) says whether the current file can stay.
    """

    result = {}

    def add(path, data):
        result[path] = (data, data.__eq__)

    references = {}
    # {id: (source, pandoc's tree)} of the reference, then of the guide
    documents = {}
    for name in sorted(os.listdir(MAN)):
        match = MAN_SOURCE.match(name)
        if not match:
            continue
        source = os.path.join(MAN, name)
        page = man_page(pandoc_bin, source, date)
        result[os.path.join("man", name[: -len(".md")])] = (
            page.encode("utf-8"),
            lambda current, page=page: unchanged_man(
                current.decode("utf-8"), page
            ),
        )
        document = tree(pandoc_bin, source, MARKDOWN)
        page_id = reference_id(document, source)
        references[match["page"]] = (match["section"], page_id)
        documents[page_id] = (source, document)
    reference = set(documents)
    for name in sorted(os.listdir(GUIDE)):
        if name.endswith(".md"):
            page_id = name[: -len(".md")]
            if page_id in documents:
                raise Error(f"{name}: a page of the reference has its id")
            source = os.path.join(GUIDE, name)
            documents[page_id] = (
                source,
                tree(pandoc_bin, source, GUIDE_MARKDOWN),
            )
    site = Site()
    writers = {}
    for page_id, (source, document) in documents.items():
        if page_id in reference:
            mallard = ReferenceWriter(page_id, document, references)
            html = ReferenceHtml(page_id, document, site, references)
        else:
            mallard = MallardWriter(page_id, document)
            html = HtmlWriter(page_id, document, site)
        page = written(mallard, source)
        add(os.path.join("mallard", page_id + ".page"), page.encode("utf-8"))
        writers[page_id] = (source, html)
    for page_id, (source, html) in writers.items():
        site.add(html.page_info())
    # their lines in the index, once every page is known to their links
    for page_id, (source, html) in writers.items():
        try:
            site.pages[page_id].desc = html.inlines(site.pages[page_id].desc)
        except Error as exc:
            raise Error(f"{source}: {exc}") from None
    for page_id, (source, html) in writers.items():
        api = documents[page_id][1]["pandoc-api-version"]
        try:
            page = html_page(pandoc_bin, html, api)
        except Error as exc:
            raise Error(f"{source}: {exc}") from None
        add(os.path.join("html", page_id + ".html"), page.encode("utf-8"))
    with open(os.path.join(TEMPLATES, "style.css"), "rb") as fp:
        add(os.path.join("html", "style.css"), fp.read())
    figures = os.path.join(GUIDE, "figures")
    for name in sorted(os.listdir(figures)) if os.path.isdir(figures) else []:
        with open(os.path.join(figures, name), "rb") as fp:
            data = fp.read()
        add(os.path.join("mallard", "figures", name), data)
        add(os.path.join("html", "figures", name), data)
    return result


def built_files():
    """The files under BUILT, as paths relative to it."""

    found = set()
    for parent, _dirs, names in os.walk(BUILT):
        for name in names:
            found.add(os.path.relpath(os.path.join(parent, name), BUILT))
    return found


def build(check=False):
    """
    Build every output; return the files that are, or were, out of date: those
    to write, and those to remove.
    """

    wanted = outputs(pandoc_path(), today())
    write = []
    for path, (data, unchanged) in sorted(wanted.items()):
        target = os.path.join(BUILT, path)
        if os.path.exists(target):
            with open(target, "rb") as fp:
                if unchanged(fp.read()):
                    continue
        write.append(path)
    remove = sorted(built_files() - set(wanted))
    if not check:
        for path in write:
            target = os.path.join(BUILT, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fp:
                fp.write(wanted[path][0])
        for path in remove:
            os.remove(os.path.join(BUILT, path))
        # the folders left empty, as figures/ without pictures
        for parent, dirs, names in os.walk(BUILT, topdown=False):
            if parent != BUILT and not dirs and not names:
                os.rmdir(parent)
    return write, remove


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing, exit with 1 if an output is out of date",
    )
    args = parser.parse_args(argv)
    try:
        write, remove = build(args.check)
    except Error as exc:
        print(f"build.py: {exc}", file=sys.stderr)
        return 2
    for names, done in ((write, "built"), (remove, "removed")):
        for name in names:
            path = os.path.relpath(os.path.join(BUILT, name), ROOT)
            print(f"{path} is out of date" if args.check else f"{done} {path}")
    return 1 if args.check and (write or remove) else 0


if __name__ == "__main__":
    sys.exit(main())
