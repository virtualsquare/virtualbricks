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

from virtualbricks.emoji import NAMES
from virtualbricks.markdown import (
    EMOJI_NAME,
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

    def test_tables(self):
        # after a line of text, as a README keeps its lines
        text = "Hosts:\n| a | b | c |\n|:--|:-:|--:|\n| 1 | *2* |\n"
        tokens = parse(text)
        self.assertEqual(
            [t.type for t in tokens if t.type.endswith("_open")],
            ["paragraph_open", "table_open", "thead_open", "tr_open"]
            + ["th_open"] * 3
            + ["tbody_open", "tr_open"]
            + ["td_open"] * 3,
        )
        self.assertEqual(
            [t.attrGet("style") for t in tokens if t.type == "th_open"],
            ["text-align:left", "text-align:center", "text-align:right"],
        )
        # a row short of a cell has it empty
        self.assertEqual(
            [plain_text(children) for children in inlines(text)],
            ["Hosts:", "a", "b", "c", "1", "2", ""],
        )

    def test_escapes_and_entities(self):
        [children] = inlines("\\*not italic\\* &amp; &copy;")
        self.assertEqual(plain_text(children), "*not italic* & ©")
        self.assertNotIn("em_open", [c.type for c in children])

    def test_what_stays_text(self):
        text = (
            "<div>html</div>\n\n"
            "    indented\n\n"
            "[ref]: https://a.org\n\n"
            "- [ ] a task\n\n"
            "[a link](javascript:alert(1))\n"
        )
        kinds_of_blocks = {kind for kind, _ in blocks(text)}
        self.assertNotIn("html_block", kinds_of_blocks)
        self.assertNotIn("code_block", kinds_of_blocks)
        texts = [plain_text(children) for children in inlines(text)]
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

    def test_emoji(self):
        text = (
            ":tada: Done :+1:, (:rocket:)\n"
            ":white_check_mark::warning: [a :bug:](https://a.org/:bug:)"
        )
        self.assertEqual(
            [plain_text(children) for children in inlines(text)],
            [
                "\U0001f389 Done \U0001f44d, (\U0001f680)\n\u2705\u26a0\ufe0f a \U0001f41b"
            ],
        )
        self.assertEqual(
            links(text), [("https://a.org/:bug:", "a \U0001f41b")]
        )
        # in a heading, an emphasis and a table too
        self.assertEqual(
            [
                plain_text(children)
                for children in inlines("# :fire:\n\n*:x:*\n\n| :ok: |\n|---|")
            ],
            ["\U0001f525", "\u274c", "\U0001f197"],
        )

    def test_emoji_names_that_stay_text(self):
        for text in (
            # addresses, where :ab: :a: :b: :100: are names
            "52:54:00:ab:cd:ef",
            "fd00:a:b::100:1",
            "at 10:30:45",
            # stuck to a word
            "word:smile: and :smile:word",
            # not a name, or a row with one that isn't
            ":nope: :tada::nope: :Smile:",
            # escaped
            "\\:smile:",
        ):
            [children] = inlines(text)
            self.assertNotIn("\U0001f604", plain_text(children), text)
            self.assertEqual(plain_text(children), text.replace("\\:", ":"))
        [children] = inlines("`:smile:`")
        self.assertEqual(children[0].content, ":smile:")
        [fence] = [t for t in parse("```\n:smile:\n```") if t.type == "fence"]
        self.assertEqual(fence.content, ":smile:\n")

    def test_every_emoji_name_can_be_written(self):
        self.assertGreater(len(NAMES), 1800)
        self.assertEqual(NAMES["smile"], "\U0001f604")
        for name in NAMES:
            self.assertTrue(EMOJI_NAME.fullmatch(f":{name}:"), name)


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

    def test_a_table(self):
        self.assertEqual(
            first_line(
                "| Host | **Address** | |\n|---|---|---|\n| r1 | a | b |"
            ),
            "Host | Address",
        )
        # the first row with text
        self.assertEqual(
            first_line("| | |\n|---|---|\n| | |\n| r1 | `a` |"), "r1 | a"
        )

    def test_emoji(self):
        self.assertEqual(
            first_line("# :tada: OSPF lab"), "\U0001f389 OSPF lab"
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
