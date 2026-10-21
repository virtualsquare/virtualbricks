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
docs/build.py: the man pages and the Mallard pages of the guide, from their
Markdown, with pandoc.

The tests are skipped when the sources of the documentation are not there, as
in an installed package, or when there is no pandoc.
"""

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import textwrap

from twisted.trial import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DOCS = os.path.join(ROOT, "docs")


def load_build():
    """docs/build.py, which isn't in a package."""

    spec = importlib.util.spec_from_file_location(
        "docs_build", os.path.join(DOCS, "build.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildTestCase(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(os.path.join(DOCS, "build.py")):
            raise unittest.SkipTest("the sources of the documentation")
        self.build = load_build()
        try:
            self.pandoc = self.build.pandoc_path()
        except self.build.Error:
            raise unittest.SkipTest("pandoc") from None


class TestUpToDate(BuildTestCase):
    """The committed outputs are those of the current sources."""

    def test_up_to_date(self):
        result = subprocess.run(
            [sys.executable, os.path.join(DOCS, "build.py"), "--check"],
            capture_output=True,
            encoding="utf-8",
            check=False,
            env={
                k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"
            },
        )
        self.assertEqual(
            result.returncode,
            0,
            f"{result.stdout}{result.stderr}run python docs/build.py",
        )


class TestMallard(BuildTestCase):
    """A page of the guide, in Mallard."""

    def page(self, markdown, name="lab"):
        folder = self.mktemp()
        os.makedirs(folder)
        path = os.path.join(folder, f"{name}.md")
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(textwrap.dedent(markdown))
        return self.build.mallard_page(self.pandoc, path)

    def body(self, markdown):
        """The lines of a page with this text after its title."""

        page = self.page("# Lab\n\n" + textwrap.dedent(markdown))
        return [line.strip() for line in page.splitlines()[4:-1]]

    def p(self, markdown):
        """The paragraph of this text."""

        (line,) = self.body(markdown)
        return line

    def assertError(self, markdown, message):
        error = self.assertRaises(self.build.Error, self.page, markdown)
        self.assertIn(message, str(error))

    def test_page(self):
        self.assertEqual(
            self.page("# The lab\n\nA lab.\n"),
            textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <page xmlns="http://projectmallard.org/1.0/" type="topic" id="lab">
                  <info/>
                  <title>The lab</title>
                  <p>A lab.</p>
                </page>
                """),  # noqa: E501
        )

    def test_front_matter(self):
        page = self.page("""\
            ---
            guide: "index#lab"
            seealso:
            - images
            - bricks
            sort: 2
            desc: The disks of a *machine*.
            ---

            # Machines
            """)
        self.assertIn(
            textwrap.indent(
                textwrap.dedent("""\
                    <info>
                      <link type="guide" xref="index#lab"/>
                      <link type="seealso" xref="images"/>
                      <link type="seealso" xref="bricks"/>
                      <title type="sort">2</title>
                      <desc>The disks of a <var>machine</var>.</desc>
                    </info>
                    """),
                "  ",
            ),
            page,
        )

    def test_guide(self):
        page = self.page("""\
            ---
            type: guide
            title-text: Virtualbricks Help
            ---

            # [Virtualbricks]{.app} Help

            ## Getting started {#start style="2column"}
            """)
        self.assertIn('type="guide" id="lab"', page)
        self.assertIn('<title type="text">Virtualbricks Help</title>', page)
        self.assertIn("<title><app>Virtualbricks</app> Help</title>", page)
        self.assertIn('<section id="start" style="2column">', page)

    def test_unknown_key(self):
        self.assertError("---\nsee: images\n---\n\n# Lab\n", "['see']")

    def test_type(self):
        self.assertError("---\ntype: faq\n---\n\n# Lab\n", "type faq")

    def test_title_first(self):
        self.assertError("A lab.\n", "starts with its title")

    def test_section(self):
        self.assertEqual(
            self.body("Before.\n\n## Disks {#disks}\n\nA disk.\n"),
            [
                "<p>Before.</p>",
                '<section id="disks">',
                "<title>Disks</title>",
                "<p>A disk.</p>",
                "</section>",
            ],
        )

    def test_section_has_its_id(self):
        # never one made from its title, which a link would lose
        self.assertError("# Lab\n\n## Disks\n", "has no id")

    def test_third_level(self):
        self.assertError("# Lab\n\n## A {#a}\n\n### B {#b}\n", "level 3")

    def test_gui(self):
        self.assertEqual(
            self.p("Click **Add Disk**."), "<p>Click <gui>Add Disk</gui>.</p>"
        )

    def test_guiseq(self):
        self.assertEqual(
            self.p("Choose **Projects › Import…**."),
            "<p>Choose <guiseq><gui>Projects</gui><gui>Import…</gui></guiseq>."
            "</p>",
        )

    def test_keys(self):
        self.assertEqual(
            self.p("[F1]{.key}, [Ctrl+Q]{.keyseq}, [Ctrl++]{.keyseq}"),
            "<p><key>F1</key>, <keyseq><key>Ctrl</key><key>Q</key></keyseq>, "
            "<keyseq><key>Ctrl</key><key>+</key></keyseq></p>",
        )

    def test_empty_key(self):
        self.assertError("# Lab\n\n[Ctrl+]{.keyseq}\n", "empty key")

    def test_code(self):
        self.assertEqual(
            self.p(
                "`info network`{.cmd} `node1`{.sys} `Downloads`{.file} "
                "`vm1_hda` `a<b`"
            ),
            "<p><cmd>info network</cmd> <sys>node1</sys> <file>Downloads</file>"
            " <code>vm1_hda</code> <code>a&lt;b</code></p>",
        )

    def test_command_with_a_part(self):
        self.assertEqual(
            self.p("[virtualbricks --run *file*]{.cmd}, *folder*"),
            "<p><cmd>virtualbricks --run <var>file</var></cmd>, "
            "<var>folder</var></p>",
        )

    def test_unknown_classes(self):
        self.assertError("# Lab\n\n`x`{.option}\n", "code of class option")
        self.assertError("# Lab\n\n[x]{.button}\n", "span of class button")

    def test_links(self):
        self.assertEqual(
            self.p(
                "[the images](images#shared), [](kinds), "
                "[**Find the File…**](images#menu), "
                "[issues](https://example.com/issues)"
            ),
            '<p><link xref="images#shared">the images</link>, '
            '<link xref="kinds"/>, '
            '<link xref="images#menu"><gui>Find the File…</gui></link>, '
            '<link href="https://example.com/issues">issues</link></p>',
        )

    def test_lists(self):
        self.assertEqual(
            self.body("- one\n- two\n\n1. first\n2. then\n"),
            [
                "<list>",
                "<item>",
                "<p>one</p>",
                "</item>",
                "<item>",
                "<p>two</p>",
                "</item>",
                "</list>",
                "<steps>",
                "<item>",
                "<p>first</p>",
                "</item>",
                "<item>",
                "<p>then</p>",
                "</item>",
                "</steps>",
            ],
        )

    def test_terms(self):
        self.assertEqual(
            self.body("""\
                ::: {.terms title="How a disk uses its image"}
                **Private copy**
                :   The default.

                    Its changes.
                :::
                """),
            [
                "<terms>",
                "<title>How a disk uses its image</title>",
                "<item>",
                "<title><gui>Private copy</gui></title>",
                "<p>The default.</p>",
                "<p>Its changes.</p>",
                "</item>",
                "</terms>",
            ],
        )

    def test_terms_div_holds_terms(self):
        self.assertError(
            '# Lab\n\n::: {.terms title="T"}\nA lab.\n:::\n', "list of terms"
        )

    def test_notes(self):
        self.assertEqual(
            self.body(
                "::: note\nA note.\n:::\n\n::: {.note .tip}\nA tip.\n:::\n"
            ),
            [
                "<note>",
                "<p>A note.</p>",
                "</note>",
                '<note style="tip">',
                "<p>A tip.</p>",
                "</note>",
            ],
        )

    def test_screen(self):
        page = self.page("# Lab\n\n```\ncd ~/Downloads\ntar -xzf a<b\n```\n")
        self.assertIn(
            "  <screen>cd ~/Downloads\ntar -xzf a&lt;b</screen>\n", page
        )

    def test_screen_of_a_class(self):
        self.assertError("# Lab\n\n```sh\nls\n```\n", "code block of class sh")

    def test_table(self):
        self.assertEqual(
            self.body("| A | B |\n|---|---|\n| x | y |\n"),
            [
                '<table frame="all" rules="rows">',
                "<thead>",
                "<tr>",
                "<td>",
                "<p>A</p>",
                "</td>",
                "<td>",
                "<p>B</p>",
                "</td>",
                "</tr>",
                "</thead>",
                "<tbody>",
                "<tr>",
                "<td>",
                "<p>x</p>",
                "</td>",
                "<td>",
                "<p>y</p>",
                "</td>",
                "</tr>",
                "</tbody>",
                "</table>",
            ],
        )

    def test_figure(self):
        self.assertEqual(
            self.body('![The lab](figures/lab.png){alt="Two machines."}\n'),
            [
                "<figure>",
                "<title>The lab</title>",
                '<media type="image" mime="image/png" src="figures/lab.png">',
                "<p>Two machines.</p>",
                "</media>",
                "</figure>",
            ],
        )

    def test_figure_needs_its_text(self):
        self.assertError(
            "# Lab\n\n![The lab](figures/lab.png)\n", "has no alt text"
        )

    def test_figure_of_unknown_type(self):
        self.assertError(
            '# Lab\n\n![The lab](lab.gif){alt="A lab."}\n', "unknown type"
        )

    def test_for_one_output(self):
        page = self.page("""\
            # Lab

            ::: {test="target:html"}
            On the web.
            :::
            """)
        self.assertIn(
            'xmlns:if="http://projectmallard.org/if/1.0/" type="topic"', page
        )
        self.assertIn('<p if:test="target:html">On the web.</p>', page)

    def test_nothing_dropped(self):
        # what the guide doesn't use stops the build
        self.assertError("# Lab\n\n> A quote.\n", "BlockQuote")
        self.assertError("# Lab\n\n~~gone~~\n", "Strikeout")
        self.assertError("# Lab\n\n::: aside\nA.\n:::\n", "div of class aside")


class TestBuild(BuildTestCase):
    """docs/build.py on sources of its own."""

    MAN_PAGE = textwrap.dedent("""\
        ---
        title: LAB
        section: 1
        footer: lab VERSION
        date: DATE
        ---

        # NAME

        lab - a lab
        """)

    def setUp(self):
        super().setUp()
        self.root = os.path.abspath(self.mktemp())
        for name in ("guide", "man", "built"):
            folder = os.path.join(self.root, name)
            self.patch(self.build, name.upper(), folder)
        os.makedirs(os.path.join(self.root, "guide", "figures"))
        os.makedirs(os.path.join(self.root, "man"))
        self.write("guide/index.md", "# Help\n")
        self.write("guide/figures/lab.png", "picture")
        self.write("man/lab.1.md", self.MAN_PAGE)
        self.patch(self.build, "today", lambda: "2026-10-21")
        self.epoch(None)

    def epoch(self, value):
        """SOURCE_DATE_EPOCH, until the end of the test."""

        old = os.environ.pop("SOURCE_DATE_EPOCH", None)
        if value is not None:
            os.environ["SOURCE_DATE_EPOCH"] = value
        self.addCleanup(os.environ.pop, "SOURCE_DATE_EPOCH", None)
        if old is not None:
            self.addCleanup(os.environ.__setitem__, "SOURCE_DATE_EPOCH", old)

    def write(self, path, text):
        with open(os.path.join(self.root, path), "w", encoding="utf-8") as fp:
            fp.write(text)

    def read(self, path):
        with open(os.path.join(self.root, path), encoding="utf-8") as fp:
            return fp.read()

    def test_build(self):
        self.assertEqual(
            self.build.build(),
            (
                [
                    "mallard/figures/lab.png",
                    "mallard/index.page",
                    "man/lab.1",
                ],
                [],
            ),
        )
        self.assertIn(
            "<title>Help</title>", self.read("built/mallard/index.page")
        )
        self.assertEqual(self.read("built/mallard/figures/lab.png"), "picture")
        self.assertIn('"2026\\-10\\-21"', self.read("built/man/lab.1"))
        # again: nothing to do
        self.assertEqual(self.build.build(), ([], []))

    def test_changed_and_gone(self):
        self.build.build()
        self.write("guide/index.md", "# Virtualbricks Help\n")
        os.remove(os.path.join(self.root, "guide/figures/lab.png"))
        self.assertEqual(
            self.build.build(),
            (["mallard/index.page"], ["mallard/figures/lab.png"]),
        )
        # the folder left empty goes too
        self.assertEqual(
            os.listdir(os.path.join(self.root, "built", "mallard")),
            ["index.page"],
        )

    def test_man_date(self):
        """The date of a man page changes only with its text."""

        self.build.build()
        self.patch(self.build, "today", lambda: "2026-12-01")
        self.assertEqual(self.build.build(), ([], []))
        self.write("man/lab.1.md", self.MAN_PAGE + "\n# BUGS\n\nNone.\n")
        self.assertEqual(self.build.build(), (["man/lab.1"], []))
        self.assertIn('"2026\\-12\\-01"', self.read("built/man/lab.1"))

    def test_man_date_of_a_release(self):
        """With SOURCE_DATE_EPOCH, its date is the page's."""

        self.build.build()
        self.epoch("0")
        self.patch(self.build, "today", lambda: "1970-01-01")
        self.assertEqual(self.build.build(), (["man/lab.1"], []))
        self.assertEqual(self.build.build(), ([], []))

    def test_version(self):
        self.build.build()
        self.assertIn(
            f"lab {self.build.version()}", self.read("built/man/lab.1")
        )

    def test_check_writes_nothing(self):
        out = io.StringIO()
        self.patch(sys, "stdout", out)
        self.assertEqual(self.build.main(["--check"]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "built")))
        self.assertIn("mallard/index.page is out of date\n", out.getvalue())
        self.build.build()
        self.assertEqual(self.build.main(["--check"]), 0)

    def test_error(self):
        self.write("guide/index.md", "A help without a title.\n")
        err = io.StringIO()
        self.patch(sys, "stderr", err)
        self.assertEqual(self.build.main([]), 2)
        self.assertIn("index.md: a page starts with its title", err.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.root, "built")))

    def test_missing_pandoc(self):
        self.patch(shutil, "which", lambda name: None)
        # import pypandoc fails
        self.addCleanup(sys.modules.pop, "pypandoc", None)
        self.addCleanup(sys.modules.update, dict(sys.modules))
        sys.modules["pypandoc"] = None
        err = io.StringIO()
        self.patch(sys, "stderr", err)
        self.assertEqual(self.build.main([]), 2)
        self.assertEqual(
            err.getvalue(),
            "build.py: pandoc not found: install the dev dependency group, "
            "or pandoc\n",
        )
