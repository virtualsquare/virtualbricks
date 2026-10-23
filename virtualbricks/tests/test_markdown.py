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
The README as Markdown: the syntax, its first line and paragraph, and the
paths of its pictures.
"""

from twisted.trial import unittest

from virtualbricks.markdown import (
    first_line,
    first_paragraph,
    parse,
    picture_path,
    plain_text,
)


def blocks(text):
    """The block tokens, as (type, tag)."""

    return [(t.type, t.tag) for t in parse(text) if t.type != "inline"]


def inlines(text):
    """The children of each inline token."""

    return [t.children for t in parse(text) if t.type == "inline"]


def kinds(text):
    """The types of the inline tokens of the first block."""

    return [child.type for child in inlines(text)[0]]


def links(text):
    """The links of the first block, as (href, text)."""

    result = []
    children = inlines(text)[0]
    for i, child in enumerate(children):
        if child.type == "link_open":
            result.append((child.attrGet("href"), children[i + 1].content))
    return result


class TestSyntax(unittest.TestCase):

    def test_headings(self):
        text = "# Lab\n## Addresses\n###### Deep\n\nTitle\n=====\n\nSub\n---\n"
        self.assertEqual(
            [tag for kind, tag in blocks(text) if kind == "heading_open"],
            ["h1", "h2", "h6", "h1", "h2"],
        )

    def test_a_new_line_is_a_line_of_its_own(self):
        [children] = inlines("Start the switches.\nThen the routers.")
        self.assertEqual(
            [(c.type, c.content) for c in children],
            [
                ("text", "Start the switches."),
                ("softbreak", ""),
                ("text", "Then the routers."),
            ],
        )
        self.assertEqual(len(inlines("One.\n\nTwo.")), 2)

    def test_emphasis(self):
        self.assertEqual(
            [k for k in kinds("*it* **bold** ~~old~~") if k.endswith("_open")],
            ["em_open", "strong_open", "s_open"],
        )

    def test_code(self):
        [children] = inlines("run `vtysh`")
        self.assertEqual(
            (children[1].type, children[1].content), ("code_inline", "vtysh")
        )
        [fence] = [t for t in parse("```sh\nshow ip ospf\n```") if t.block]
        self.assertEqual(
            (fence.type, fence.info, fence.content),
            ("fence", "sh", "show ip ospf\n"),
        )

    def test_lists(self):
        text = "- r1\n- r2\n  1. first\n  2. second\n"
        opened = [kind for kind, _ in blocks(text) if kind.endswith("_open")]
        self.assertEqual(
            [kind for kind in opened if "list_open" in kind],
            ["bullet_list_open", "ordered_list_open"],
        )

    def test_quotes(self):
        self.assertIn(
            ("blockquote_open", "blockquote"), blocks("> Update first.")
        )

    def test_links(self):
        self.assertEqual(
            links("[BIRD](https://bird.network.cz)"),
            [("https://bird.network.cz", "BIRD")],
        )
        self.assertEqual(
            links("<https://bird.network.cz>"),
            [("https://bird.network.cz", "https://bird.network.cz")],
        )

    def test_bare_urls(self):
        self.assertEqual(
            links("See https://bird.network.cz/doc/ and http://a.org."),
            [
                (
                    "https://bird.network.cz/doc/",
                    "https://bird.network.cz/doc/",
                ),
                ("http://a.org", "http://a.org"),
            ],
        )
        [children] = inlines("(see https://a.org/x), then")
        self.assertEqual(
            [(c.type, c.nesting, c.content) for c in children],
            [
                ("text", 0, "(see "),
                ("link_open", 1, ""),
                ("text", 0, "https://a.org/x"),
                ("link_close", -1, ""),
                ("text", 0, "), then"),
            ],
        )

    def test_bare_urls_in_links_and_code_stay(self):
        self.assertEqual(
            links("[https://a.org](https://b.org) `https://c.org`"),
            [("https://b.org", "https://a.org")],
        )
        # but one after a link is a link
        self.assertEqual(
            links("[a](https://a.org) and https://b.org"),
            [("https://a.org", "a"), ("https://b.org", "https://b.org")],
        )
        self.assertEqual(links("ftp://a.org and www.a.org"), [])

    def test_pictures(self):
        [children] = inlines("![a *map* of it](map.png)")
        [image] = children
        self.assertEqual(image.type, "image")
        self.assertEqual(image.attrGet("src"), "map.png")
        self.assertEqual(plain_text(children), "a map of it")

    def test_rule(self):
        self.assertEqual(
            blocks("One.\n\n---\n\nTwo."),
            [
                ("paragraph_open", "p"),
                ("paragraph_close", "p"),
                ("hr", "hr"),
                ("paragraph_open", "p"),
                ("paragraph_close", "p"),
            ],
        )

    def test_escapes_and_entities(self):
        [children] = inlines("\\*not italic\\* &amp; &copy;")
        self.assertEqual(plain_text(children), "*not italic* & ©")
        self.assertNotIn("em_open", [c.type for c in children])

    def test_what_stays_text(self):
        text = (
            "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
            "<div>html</div>\n\n"
            "    indented\n\n"
            "[ref]: https://a.org\n\n"
            "- [ ] a task\n\n"
            "[a link](javascript:alert(1))\n"
        )
        kinds_of_blocks = {kind for kind, _ in blocks(text)}
        self.assertNotIn("table_open", kinds_of_blocks)
        self.assertNotIn("html_block", kinds_of_blocks)
        self.assertNotIn("code_block", kinds_of_blocks)
        texts = [plain_text(children) for children in inlines(text)]
        self.assertIn("| a | b |\n|---|---|\n| 1 | 2 |", texts)
        self.assertIn("<div>html</div>", texts)
        self.assertIn("indented", texts)
        self.assertIn("[ref]: https://a.org", texts)
        self.assertIn("[ ] a task", texts)
        # no link to a script
        self.assertEqual(links("[a link](javascript:alert(1))"), [])

    def test_names_keep_their_underscores(self):
        [children] = inlines("vm1_hda and vm2_hdb")
        self.assertEqual(
            [(c.type, c.content) for c in children],
            [("text", "vm1_hda and vm2_hdb")],
        )


class TestFirstLine(unittest.TestCase):

    def test_a_heading(self):
        self.assertEqual(
            first_line("# OSPF lab\n\nThree routers."), "OSPF lab"
        )

    def test_without_the_marks(self):
        self.assertEqual(
            first_line("**Three** routers, `r1` and [r2](https://a.org)\nr3"),
            "Three routers, r1 and r2",
        )

    def test_the_first_block_with_text(self):
        self.assertEqual(first_line("---\n\nAfter the rule"), "After the rule")
        self.assertEqual(first_line("- first item\n- second"), "first item")
        self.assertEqual(first_line("```\nvtysh\nexit\n```"), "vtysh")
        self.assertEqual(first_line("```\n\n```\n\nText"), "Text")
        self.assertEqual(
            first_line("![a *map*](m.png) of the lab"), "a map of the lab"
        )

    def test_a_readme_written_as_plain_text(self):
        self.assertEqual(first_line("Router r1\nRouter r2"), "Router r1")

    def test_nothing(self):
        self.assertEqual(first_line(""), "")
        self.assertEqual(first_line("\n\n  \n"), "")


class TestFirstParagraph(unittest.TestCase):

    def test_after_the_heading(self):
        text = "# Lab\n\nThree routers.\nOne **switch**.\n\nMore."
        self.assertEqual(
            first_paragraph(text), "Three routers.\nOne **switch**."
        )

    def test_only_at_the_top(self):
        text = "- in a list\n\n> in a quote\n\nThe paragraph.\n"
        self.assertEqual(first_paragraph(text), "The paragraph.")

    def test_windows_line_ends(self):
        text = "# Lab\r\n\r\nLine one\r\nLine two\r\n"
        self.assertEqual(first_paragraph(text), "Line one\nLine two")

    def test_none(self):
        self.assertEqual(first_paragraph("# Only a heading\n\n- a list"), "")
        self.assertEqual(first_paragraph(""), "")


def src(text):
    [children] = inlines(text)
    [image] = children
    return image.attrGet("src")


class TestPicturePath(unittest.TestCase):

    def test_a_path_in_the_folder(self):
        self.assertEqual(picture_path(src("![a](map.png)")), "map.png")
        self.assertEqual(
            picture_path(src("![a](pictures/map.png)")), "pictures/map.png"
        )
        # the folder is checked when it's read
        self.assertEqual(picture_path(src("![a](../map.png)")), "../map.png")

    def test_the_characters_the_parser_writes_as_a_url(self):
        self.assertEqual(
            picture_path(src("![a](<the map.png>)")), "the map.png"
        )
        self.assertEqual(picture_path(src("![a](café.png)")), "café.png")
        self.assertEqual(
            picture_path(src("![a](the%20map.png)")), "the map.png"
        )

    def test_a_query_or_a_fragment_ends_it(self):
        self.assertEqual(picture_path(src("![a](map.png?raw=1)")), "map.png")
        self.assertEqual(picture_path(src("![a](map.png#top)")), "map.png")

    def test_not_a_path_in_the_folder(self):
        for text in (
            "![a](https://a.org/map.png)",
            "![a](//a.org/map.png)",
            "![a](/home/me/map.png)",
            "![a](data:image/png;base64,AAAA)",
            "![a]()",
            "![a](?raw=1)",
        ):
            self.assertIsNone(picture_path(src(text)), text)
