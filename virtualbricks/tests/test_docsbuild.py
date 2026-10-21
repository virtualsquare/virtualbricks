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

    def test_nothing_dropped(self):
        # what the guide doesn't use stops the build
        self.assertError("# Lab\n\n> A quote.\n", "BlockQuote")
        self.assertError("# Lab\n\n~~gone~~\n", "Strikeout")
        self.assertError("# Lab\n\n::: aside\nA.\n:::\n", "div of class aside")
        # the conditions of Mallard: the reference is in the guide
        self.assertError(
            '# Lab\n\n::: {test="target:html"}\nA.\n:::\n', "div of class"
        )


class TestReference(BuildTestCase):
    """A man page, as a page of the reference in the guide."""

    FRONT = textwrap.dedent("""\
        ---
        title: LAB
        section: 1
        footer: lab VERSION
        date: DATE
        help:
          id: lab-line
          title: The lab line
        guide: "index#reference"
        sort: 1
        ---

        # NAME

        lab - labs of machines, and their *console*

        """)
    # the man pages of the reference, by their names
    REFERENCES = {"lab": ("1", "lab-line"), "lab-config": ("5", "lab-files")}

    def document(self, markdown, front=None):
        folder = self.mktemp()
        os.makedirs(folder)
        path = os.path.join(folder, "lab.1.md")
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(self.FRONT if front is None else front)
            fp.write(textwrap.dedent(markdown))
        return path, self.build.tree(self.pandoc, path, self.build.MARKDOWN)

    def page(self, markdown, front=None):
        path, document = self.document(markdown, front)
        page_id = self.build.reference_id(document, path)
        writer = self.build.ReferenceWriter(page_id, document, self.REFERENCES)
        return self.build.written(writer, path)

    def body(self, markdown):
        """The lines of the page after its list of sections."""

        lines = [line.strip() for line in self.page(markdown).splitlines()]
        return lines[lines.index('<links type="section"/>') + 1 : -1]

    def p(self, markdown):
        """The paragraph of this text, in a section."""

        lines = self.body("# DESCRIPTION\n\n" + markdown)
        (line,) = lines[2:-1]
        return line

    def assertError(self, markdown, message, front=None):
        error = self.assertRaises(self.build.Error, self.page, markdown, front)
        self.assertIn(message, str(error))

    def test_page(self):
        self.assertEqual(
            self.page("# DESCRIPTION\n\nA lab.\n"),
            textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <page xmlns="http://projectmallard.org/1.0/" type="topic" id="lab-line">
                  <info>
                    <link type="guide" xref="index#reference"/>
                    <title type="sort">1</title>
                    <desc>lab(1): labs of machines, and their <var>console</var></desc>
                  </info>
                  <title>The lab line</title>
                  <links type="section"/>
                  <section id="description">
                    <title>Description</title>
                    <p>A lab.</p>
                  </section>
                </page>
                """),  # noqa: E501
        )

    def test_synopsis(self):
        self.assertEqual(
            self.body("# SYNOPSIS\n\n**lab** *file*\\\n**lab** **--help**\n"),
            [
                '<section id="synopsis">',
                "<title>Synopsis</title>",
                "<synopsis>",
                "<p><code>lab</code> <var>file</var></p>",
                "<p><code>lab</code> <code>--help</code></p>",
                "</synopsis>",
                "</section>",
            ],
        )

    def test_line_break_elsewhere(self):
        self.assertError("# DESCRIPTION\n\nOne\\\ntwo\n", "line break")

    def test_marks(self):
        # bold is literal text, italics a part to replace
        self.assertEqual(
            self.p("**--listen** **unix:***path***:protocol=json**, `ls`"),
            "<p><code>--listen</code> <code>unix:</code><var>path</var>"
            "<code>:protocol=json</code>, <code>ls</code></p>",
        )

    def test_headings(self):
        self.assertEqual(
            [line for line in self.body("""\
                    # THE JSON PROTOCOL

                    ## The **Hello** box

                    ### TOML OF VIRTUALBRICKS

                    # CONTENTS.TOML {title="contents.toml"}
                    """) if line.startswith(("<title>", "<section"))],
            [
                '<section id="the-json-protocol">',
                "<title>The JSON protocol</title>",
                '<section id="the-hello-box">',
                "<title>The <code>Hello</code> box</title>",
                '<section id="toml-of-virtualbricks">',
                "<title>TOML of Virtualbricks</title>",
                '<section id="contents.toml">',
                "<title>contents.toml</title>",
            ],
        )

    def test_sections_nest(self):
        body = self.body("# ONE\n\n## Two\n\n### Three\n\n# FOUR\n")
        self.assertEqual(
            [line for line in body if "section" in line],
            [
                '<section id="one">',
                '<section id="two">',
                '<section id="three">',
                "</section>",
                "</section>",
                "</section>",
                '<section id="four">',
                "</section>",
            ],
        )

    def test_levels(self):
        self.assertError("## Two\n", "level 2 there: Two")
        self.assertError("# ONE\n\n### Three\n", "level 3 there")
        self.assertError(
            "# ONE\n\n## Two\n\n### Three\n\n#### Four\n", "level 4"
        )

    def test_cross_references(self):
        self.assertEqual(
            self.p(
                "**lab-config**(5), **lab**(1), **lab-config**(7), "
                "**tar**(1)."
            ),
            '<p><link xref="lab-files">lab-config(5)</link>, '
            "<code>lab</code>(1), <code>lab-config</code>(7), "
            "<code>tar</code>(1).</p>",
        )

    def test_numbered(self):
        # not a procedure
        self.assertIn(
            '<list type="numbered">', self.body("# ORDER\n\n1. one\n2. two\n")
        )

    def test_front_matter(self):
        front = self.FRONT.replace("sort: 1\n", "sort: 1\nseealso: lab\n")
        self.assertError("", "['seealso']", front)

    def test_help_in_front_matter(self):
        front = self.FRONT.replace("  id: lab-line\n", "")
        self.assertError("", "an id and a title", front)
        front = self.FRONT.replace("help:\n  id: lab-line\n", "x:\n  i: l\n")
        self.assertError("", "no help", front)

    def test_name(self):
        front = self.FRONT.split("# NAME")[0]
        self.assertError("# DESCRIPTION\n\nA lab.\n", "has its NAME", front)
        self.assertError("# NAME\n\nlab, a lab\n", "name - what it is", front)


class TestBuild(BuildTestCase):
    """docs/build.py on sources of its own."""

    MAN_PAGE = textwrap.dedent("""\
        ---
        title: LAB
        section: 1
        footer: lab VERSION
        date: DATE
        help:
          id: lab
          title: The lab
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
                    "html/figures/lab.png",
                    "html/index.html",
                    "html/lab.html",
                    "html/style.css",
                    "mallard/figures/lab.png",
                    "mallard/index.page",
                    "mallard/lab.page",
                    "man/lab.1",
                ],
                [],
            ),
        )
        self.assertIn(
            "<title>Help</title>", self.read("built/mallard/index.page")
        )
        self.assertIn(
            "<title>The lab</title>", self.read("built/mallard/lab.page")
        )
        self.assertEqual(self.read("built/mallard/figures/lab.png"), "picture")
        self.assertIn('"2026\\-10\\-21"', self.read("built/man/lab.1"))
        # again: nothing to do
        self.assertEqual(self.build.build(), ([], []))

    def test_changed_and_gone(self):
        self.build.build()
        self.write("guide/index.md", "# Virtualbricks Help\n")
        os.remove(os.path.join(self.root, "guide/figures/lab.png"))
        # the title of the index is in those of the other pages
        self.assertEqual(
            self.build.build(),
            (
                ["html/index.html", "html/lab.html", "mallard/index.page"],
                ["html/figures/lab.png", "mallard/figures/lab.png"],
            ),
        )
        # the folder left empty goes too
        self.assertEqual(
            sorted(os.listdir(os.path.join(self.root, "built", "mallard"))),
            ["index.page", "lab.page"],
        )
        self.assertNotIn(
            "figures", os.listdir(os.path.join(self.root, "built", "html"))
        )

    def test_one_id_each(self):
        """A page of the guide can't take the id of one of the reference."""

        self.write("guide/lab.md", "# A lab\n")
        error = self.assertRaises(self.build.Error, self.build.build)
        self.assertEqual(
            str(error), "lab.md: a page of the reference has its id"
        )

    def test_man_date(self):
        """The date of a man page changes only with its text."""

        self.build.build()
        self.patch(self.build, "today", lambda: "2026-12-01")
        self.assertEqual(self.build.build(), ([], []))
        self.write("man/lab.1.md", self.MAN_PAGE + "\n# BUGS\n\nNone.\n")
        # and its page in the guide
        self.assertEqual(
            self.build.build(),
            (["html/lab.html", "mallard/lab.page", "man/lab.1"], []),
        )
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


class TestHtml(BuildTestCase):
    """The HTML of the guide and of its reference, on a site of its own."""

    INDEX = textwrap.dedent("""\
        ---
        type: guide
        title-text: Lab Help
        ---

        # [Lab]{.app} Help

        ## Your lab {#lab style="2column"}

        ## Reference {#reference}
        """)

    def setUp(self):
        super().setUp()
        self.root = os.path.abspath(self.mktemp())
        for name in ("guide", "man", "built"):
            self.patch(self.build, name.upper(), os.path.join(self.root, name))
        os.makedirs(os.path.join(self.root, "guide", "figures"))
        os.makedirs(os.path.join(self.root, "man"))
        self.write("guide/index.md", self.INDEX)

    def write(self, path, text):
        with open(os.path.join(self.root, path), "w", encoding="utf-8") as fp:
            fp.write(textwrap.dedent(text))

    def html(self, name):
        self.build.build()
        path = os.path.join(self.root, "built", "html", f"{name}.html")
        with open(path, encoding="utf-8") as fp:
            # pandoc wraps lines: the text, as one line
            return " ".join(fp.read().split())

    def topic(self, name, body, **meta):
        front = "".join(f"{key}: {value}\n" for key, value in meta.items())
        self.write(f"guide/{name}.md", f"---\n{front}---\n\n{body}")

    def test_marks(self):
        self.topic(
            "a",
            "# A\n\n**Add Disk**, **Projects › Import…**, [F1]{.key}, "
            "[Ctrl+Q]{.keyseq}, `ls`{.cmd}, [lab --run *file*]{.cmd}\n",
        )
        html = self.html("a")
        for part in (
            '<span class="gui">Add Disk</span>',
            '<span class="guiseq"><span class="gui">Projects</span> › '
            '<span class="gui">Import…</span></span>',
            "<kbd>F1</kbd>",
            "<kbd>Ctrl</kbd>+<kbd>Q</kbd>",
            '<code class="cmd">ls</code>',
            '<span class="cmd">lab --run <em>file</em></span>',
        ):
            self.assertIn(part, html)

    def test_title(self):
        self.topic("a", "# A page\n")
        self.assertIn("<title>A page — Lab Help</title>", self.html("a"))
        self.assertIn("<title>Lab Help</title>", self.html("index"))
        self.assertIn(
            '<link rel="stylesheet" href="style.css">', self.html("a")
        )

    def test_links(self):
        self.topic("a", "# A\n\n[](b), [](b#disks), [the disks](b#disks)\n")
        self.topic("b", "# Machines\n\n## The disks {#disks}\n")
        self.assertIn(
            '<a href="b.html">Machines</a>, '
            '<a href="b.html#disks">The disks</a>, '
            '<a href="b.html#disks">the disks</a>',
            self.html("a"),
        )

    def test_links_to_nowhere(self):
        self.topic("a", "# A\n\n[](b)\n")
        error = self.assertRaises(self.build.Error, self.build.build)
        self.assertIn("a page that isn't there: b", str(error))
        self.topic("a", "# A\n\n[](index#disks)\n")
        error = self.assertRaises(self.build.Error, self.build.build)
        self.assertIn("a section that isn't there: index#disks", str(error))

    def test_figure(self):
        self.write("guide/figures/lab.png", "picture")
        self.topic(
            "a", '# A\n\n![The lab](figures/lab.png){alt="Two machines."}\n'
        )
        html = self.html("a")
        self.assertIn(
            '<a href="figures/lab.png"><img src="figures/lab.png" '
            'alt="Two machines." /></a>',
            html,
        )
        self.assertIn("<figcaption>The lab</figcaption>", html)

    def test_blocks(self):
        self.topic(
            "a",
            '# A\n\n::: {.terms title="How & why"}\nterm\n:   what\n:::\n\n'
            "::: {.note .tip}\nA tip.\n:::\n",
        )
        html = self.html("a")
        self.assertIn(
            '<div class="terms"> <p class="title">How &amp; why</p>', html
        )
        self.assertIn('<div class="note tip"> <p>A tip.</p> </div>', html)

    def test_index(self):
        self.topic(
            "a",
            "# Bricks\n",
            guide='"index#lab"',
            sort="2",
            desc="Start them.",
        )
        self.topic("b", "# Machines\n", guide='"index#lab"', sort="1")
        html = self.html("index")
        self.assertIn('<h2 class="columns" id="lab">Your lab</h2>', html)
        self.assertIn(
            '<div class="links"> <div class="link"> <p><a href="b.html">'
            'Machines</a></p> </div> <div class="link"> <p><a href="a.html">'
            'Bricks</a></p> <div class="desc"> <p>Start them.</p> </div>',
            html,
        )

    def test_trail(self):
        self.topic("a", "# Bricks\n", guide='"index#lab"')
        self.assertIn(
            '<div class="trail"> <p><a href="index.html">Lab Help</a> › '
            '<a href="index.html#lab">Your lab</a></p> </div>',
            self.html("a"),
        )
        self.assertNotIn("trail", self.html("index"))

    def test_see_also_both_ways(self):
        self.topic("a", "# Bricks\n", seealso="[b]", desc="Start them.")
        self.topic("b", "# Machines\n\n## Disks {#disks}\n", seealso='["c#x"]')
        self.topic("c", "# Events\n\n## X {#x}\n")
        self.assertIn('<a href="b.html">Machines</a>', self.html("a"))
        see_also = self.html("b").split('id="seealso"')[1]
        self.assertIn('<a href="a.html">Bricks</a>', see_also)
        self.assertIn("Start them.", see_also)
        # a section, by its title
        self.assertIn('<a href="c.html#x">X</a>', see_also)
        self.assertIn('<a href="b.html">Machines</a>', self.html("c"))

    def test_reference(self):
        front = textwrap.dedent("""\
            ---
            title: LAB
            section: {section}
            help:
              id: {id}
              title: {title}
            guide: "index#reference"
            ---

            # NAME

            {name} - the **lab** of *machines*

            """)
        self.write(
            "man/lab.1.md",
            front.format(
                id="line", title="The command line", name="lab", section=1
            )
            + "# SYNOPSIS\n\n**lab** *file*\\\n**lab** **--help**\\\n"
            "**lab** **unix:***path***:x**\n\n"
            "# THE JSON PROTOCOL\n\n## Hello\n\nSee **lab-config**(5).\n",
        )
        self.write(
            "man/lab-config.5.md",
            front.format(
                id="files",
                title="Configuration files",
                name="lab-config",
                section=5,
            )
            + "# FILES\n\nNone.\n",
        )
        html = self.html("line")
        for part in (
            "<h1>The command line</h1>",
            '<div class="lede"> <p>the <code>lab</code> of <em>machines</em></p>',
            f"lab(1) · Virtualbricks {self.build.version()}",
            '<div class="synopsis"> <p><code>lab</code> <em>file</em><br />',
            # side by side, one code
            "<code>lab</code> <code>unix:<em>path</em>:x</code></p>",
            '<h2 id="the-json-protocol">The JSON protocol</h2>',
            '<h3 id="hello">Hello</h3>',
            'See <a href="files.html">lab-config(5)</a>.',
            '<li><a href="#synopsis">Synopsis</a></li>',
            '<li><a href="#the-json-protocol">The JSON protocol</a></li>',
            '<div class="page reference">',
        ):
            self.assertIn(part, html)
        self.assertNotIn('href="#hello"', html)
        self.assertNotIn("NAME", html)
        index = self.html("index")
        self.assertIn(
            '<a href="line.html">The command line</a></p> <div class="desc"> '
            "<p>lab(1): the <code>lab</code> of <em>machines</em></p>",
            index,
        )


class TestReferenceHtml(BuildTestCase):
    """A man page in HTML: its keys, its powers, its diagrams."""

    FRONT = textwrap.dedent("""\
        ---
        title: LAB
        section: 5
        help:
          id: lab
          title: Lab files
        ---

        # NAME

        lab - the files of a lab

        # SETTINGS

        """)
    ASCII = "```\n+-----+\n| lab |\n+-----+\n```\n\n"

    def setUp(self):
        super().setUp()
        self.root = os.path.abspath(self.mktemp())
        for name in ("guide", "man", "built"):
            self.patch(self.build, name.upper(), os.path.join(self.root, name))
        os.makedirs(os.path.join(self.root, "guide"))
        os.makedirs(os.path.join(self.root, "man", "figures"))
        with open(
            os.path.join(self.root, "man", "figures", "lab.svg"), "w"
        ) as fp:
            fp.write('<svg class="dg"><text>lab</text></svg>\n')

    def built(self, markdown, kind="html"):
        path = os.path.join(self.root, "man", "lab.5.md")
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(self.FRONT + textwrap.dedent(markdown))
        self.build.build()
        name = "lab.html" if kind == "html" else "lab.page"
        built = os.path.join(self.root, "built", kind, name)
        with open(built, encoding="utf-8") as fp:
            return " ".join(fp.read().split())

    def test_keys(self):
        html = self.built("""\
            **ports** = *integer* 1-128, default `32`
            :   The number of ports.

            **delay** = *integer* 0-2^31-1
            :   The delay.
            """)
        for part in (
            '<table class="keys">',
            "<th>Key</th> <th>Type</th> <th>Default</th> <th>Meaning</th>",
            "<td><code>ports</code></td> <td><em>integer</em> 1–128</td> "
            "<td><code>32</code></td> <td>The number of ports.</td>",
            "<td><em>integer</em> 0–2<sup>31</sup>−1</td> <td></td>",
        ):
            self.assertIn(part, html)
        self.assertNotIn("<dl>", html)

    def test_keys_without_defaults(self):
        html = self.built("**path** = *string*\n:   The archive.\n")
        self.assertIn("<th>Key</th> <th>Type</th> <th>Meaning</th>", html)

    def test_not_all_keys(self):
        # a list with a term that isn't a key stays a list
        html = self.built(
            "**ports** = *integer*\n:   Ports.\n\n**hub**\n:   A hub.\n"
        )
        self.assertNotIn("<table", html)
        self.assertIn("<dl>", html)

    def test_powers(self):
        self.assertIn(
            "Up to 2<sup>53</sup>−1 bytes, 2<sup>8</sup> of them",
            self.built("Up to 2^53-1 bytes, 2^8 of them.\n"),
        )

    def test_diagram(self):
        markdown = (
            '::: {.diagram svg="figures/lab.svg"}\n'
            + self.ASCII
            + "The **lab**, drawn.\n:::\n"
        )
        html = self.built(markdown)
        self.assertIn(
            '<figure class="diagram"> <div class="canvas"> '
            '<svg class="dg"><text>lab</text></svg> </div> '
            "<figcaption>The <code>lab</code>, drawn.</figcaption> </figure>",
            html,
        )
        # the drawing in place of the ASCII
        self.assertNotIn("+-----+", html)
        page = self.built(markdown, "mallard")
        self.assertIn(
            "<figure> <desc>The <code>lab</code>, drawn.</desc> "
            "<screen>+-----+ | lab | +-----+</screen> </figure>",
            page,
        )

    def test_listing(self):
        html = self.built(
            '::: {.diagram .listing svg="figures/lab.svg"}\n'
            + self.ASCII
            + "The lab.\n:::\n"
        )
        # the drawing, then the listing
        self.assertIn("</figure> <pre><code>+-----+", html)

    def test_diagram_without_its_drawing(self):
        error = self.assertRaises(
            self.build.Error,
            self.built,
            '::: {.diagram svg="figures/gone.svg"}\n'
            + self.ASCII
            + "Gone.\n:::\n",
        )
        self.assertIn("the drawing figures/gone.svg isn't there", str(error))

    def test_diagram_is_ascii_and_caption(self):
        error = self.assertRaises(
            self.build.Error,
            self.built,
            '::: {.diagram svg="figures/lab.svg"}\n' + self.ASCII + ":::\n",
        )
        self.assertIn("a code block, then its caption", str(error))
