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
                                    copy of its pictures in figures/

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
import subprocess
import sys
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUIDE = os.path.join(HERE, "guide")
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
IF_NS = "http://projectmallard.org/if/1.0/"
# The keys of the front matter of a page of the guide
GUIDE_META = {"type", "guide", "seealso", "sort", "desc", "title-text"}
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


def keys(sequence):
    """The keys of Ctrl+Q; of Ctrl++, Ctrl and the key +."""

    if sequence.endswith("++"):
        result = sequence[:-2].split("+") + ["+"]
    else:
        result = sequence.split("+")
    if "" in result:
        raise Error(f"a key sequence with an empty key: {sequence}")
    return result


def meta_list(value):
    if value["t"] == "MetaList":
        return [meta_text(item) for item in value["c"]]
    return [meta_text(value)]


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


def para(tag, inlines, attrs=None):
    return Element(tag, attrs, MallardWriter.inlines(inlines), inline=True)


class MallardWriter:
    """
    A page of the guide, from pandoc's tree of its Markdown: the marks of
    docs/README.md become the elements of Mallard. Anything else is an
    error: the writer never drops a part of a page.
    """

    def __init__(self, name, document):
        self.name = name
        self.document = document
        self.uses_if = False

    # Inlines

    @classmethod
    def inlines(cls, inlines):
        """Text and elements, the spaces collapsed."""

        result = []
        for inline in inlines:
            for item in cls.inline(inline):
                if (
                    isinstance(item, str)
                    and result
                    and isinstance(result[-1], str)
                ):
                    result[-1] += item
                else:
                    result.append(item)
        return result

    @classmethod
    def inline(cls, inline):
        kind = inline["t"]
        content = inline.get("c")
        if kind == "Str":
            return [content]
        if kind in ("Space", "SoftBreak"):
            return [" "]
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
        if kind == "Emph":
            return [Element("var", children=cls.inlines(content))]
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
                return [Element(classes[0], children=cls.inlines(spanned))]
            raise Error(
                f"a span of class {' '.join(classes)}: {text(spanned)}"
            )
        if kind == "Link":
            _attr, linked, (target, _title) = content
            attr = (
                "href" if re.match(r"^[a-z][a-z0-9+.-]*:", target) else "xref"
            )
            return [Element("link", {attr: target}, cls.inlines(linked))]
        raise Error(f"{kind}, which the guide doesn't use")

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
            return [para("p", content)]
        if kind == "BulletList":
            return [Element("list", children=self.items(content))]
        if kind == "OrderedList":
            return [Element("steps", children=self.items(content[1]))]
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
        raise Error(f"{kind}, which the guide doesn't use")

    def items(self, items):
        return [
            Element("item", children=self.blocks(blocks)) for blocks in items
        ]

    def terms(self, items):
        result = []
        for term, definitions in items:
            children = [para("title", term)]
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
            [para("p", alt)],
        )
        return Element(
            "figure", children=[para("title", caption[0]["c"]), media]
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
            title = para("title", self.markdown_inlines(attrs["title"]))
            inner[0].children.insert(0, title)
            return inner
        if classes[:1] == ["note"] and not attrs and len(classes) <= 2:
            note = Element("note", children=self.blocks(blocks))
            if len(classes) == 2:
                note.attrs["style"] = classes[1]
            return [note]
        if not classes and set(attrs) == {"test"}:
            # the conditions of Mallard: a part for one output only
            self.uses_if = True
            inner = self.blocks(blocks)
            for element in inner:
                element.attrs["if:test"] = attrs["test"]
            return inner
        raise Error(f"a div of class {' '.join(classes)} {attrs}")

    @staticmethod
    def markdown_inlines(value):
        """A title given as an attribute: its text, as words."""

        words = []
        for index, word in enumerate(value.split()):
            if index:
                words.append({"t": "Space"})
            words.append({"t": "Str", "c": word})
        return words

    # The page

    def info(self, meta):
        unknown = set(meta) - GUIDE_META
        if unknown:
            raise Error(f"unknown keys in the front matter: {sorted(unknown)}")
        children = []
        for xref in meta_list(meta["guide"]) if "guide" in meta else []:
            children.append(Element("link", {"type": "guide", "xref": xref}))
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
        if "sort" in meta:
            children.append(
                Element(
                    "title",
                    {"type": "sort"},
                    [meta_text(meta["sort"])],
                    inline=True,
                )
            )
        if "desc" in meta:
            value = meta["desc"]
            inlines = value["c"] if value["t"] == "MetaInlines" else None
            if inlines is None:
                inlines = self.markdown_inlines(meta_text(value))
            children.append(para("desc", inlines))
        return Element("info", children=children)

    def page(self):
        meta = self.document["meta"]
        blocks = self.document["blocks"]
        if not blocks or blocks[0]["t"] != "Header" or blocks[0]["c"][0] != 1:
            raise Error("a page starts with its title, # Title")
        kind = meta_text(meta["type"]) if "type" in meta else "topic"
        if kind not in ("topic", "guide"):
            raise Error(f"a page of type {kind}")
        children = [self.info(meta), para("title", blocks[0]["c"][2])]
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
                section.children.append(para("title", title))
                children.append(section)
            else:
                target = children if section is None else section.children
                target.extend(self.block(block))
        attrs = {"xmlns": MALLARD_NS}
        if self.uses_if:
            attrs["xmlns:if"] = IF_NS
        attrs.update({"type": kind, "id": self.name})
        root = Element("page", attrs, children)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            + "\n".join(root.lines())
            + "\n"
        )


def mallard_page(pandoc_bin, source):
    tree = pandoc(
        pandoc_bin,
        ["--standalone", f"--from={GUIDE_MARKDOWN}", "--to=json"],
        read(source),
        source,
    )
    name = os.path.basename(source)[: -len(".md")]
    try:
        return MallardWriter(name, json.loads(tree)).page()
    except Error as exc:
        raise Error(f"{source}: {exc}") from None


# The outputs


def outputs(pandoc_bin, date):
    """
    Every output, as {path relative to BUILT: (content, unchanged)}, where
    unchanged(current) says whether the current file can stay.
    """

    result = {}
    for name in sorted(os.listdir(MAN)):
        match = MAN_SOURCE.match(name)
        if match:
            page = man_page(pandoc_bin, os.path.join(MAN, name), date)
            result[os.path.join("man", name[: -len(".md")])] = (
                page.encode("utf-8"),
                lambda current, page=page: unchanged_man(
                    current.decode("utf-8"), page
                ),
            )
    for name in sorted(os.listdir(GUIDE)):
        if name.endswith(".md"):
            page = mallard_page(pandoc_bin, os.path.join(GUIDE, name))
            path = os.path.join("mallard", name[: -len(".md")] + ".page")
            data = page.encode("utf-8")
            result[path] = (data, data.__eq__)
    figures = os.path.join(GUIDE, "figures")
    for name in sorted(os.listdir(figures)) if os.path.isdir(figures) else []:
        with open(os.path.join(figures, name), "rb") as fp:
            data = fp.read()
        result[os.path.join("mallard", "figures", name)] = (data, data.__eq__)
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
