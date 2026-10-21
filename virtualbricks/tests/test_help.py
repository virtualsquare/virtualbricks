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
The user guide: the Mallard pages of docs/built/mallard/, which docs/build.py
writes from their Markdown, their pictures in docs/guide/figures/, and their
HTML in help/html/C/, which help/build.py makes with the Yelp tools.

The tests of the pages are skipped when the sources of the guide are not
there, as in an installed package, and those that run yelp-check when the
Yelp tools are not installed.
"""

import filecmp
import glob
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET

from twisted.trial import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
HELP = os.path.join(ROOT, "help")
PAGES = os.path.join(ROOT, "docs", "built", "mallard")
HTML = os.path.join(HELP, "html", "C")
FIGURES = os.path.join(ROOT, "docs", "guide", "figures")
MALLARD = "{http://projectmallard.org/1.0/}"


def page_names():
    return sorted(
        os.path.basename(path)[: -len(".page")]
        for path in glob.glob(os.path.join(PAGES, "*.page"))
    )


def picture_names():
    return sorted(os.listdir(FIGURES)) if os.path.isdir(FIGURES) else []


def load_build():
    """help/build.py, which isn't in a package."""

    spec = importlib.util.spec_from_file_location(
        "help_build", os.path.join(HELP, "build.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PagesTestCase(unittest.TestCase):

    def setUp(self):
        if not os.path.isdir(PAGES):
            raise unittest.SkipTest("the sources of the guide")


class TestThePages(PagesTestCase):

    def test_every_page_has_its_html(self):
        built = sorted(
            os.path.basename(path)[: -len(".html")]
            for path in glob.glob(os.path.join(HTML, "*.html"))
        )
        self.assertEqual(built, page_names(), "run python help/build.py")

    def test_the_id_is_the_file_name(self):
        for name in page_names():
            root = ET.parse(os.path.join(PAGES, f"{name}.page")).getroot()
            self.assertEqual(root.tag, f"{MALLARD}page", name)
            self.assertEqual(root.get("id"), name)

    def test_every_topic_is_in_a_guide_section(self):
        index = ET.parse(os.path.join(PAGES, "index.page")).getroot()
        sections = {
            f"index#{section.get('id')}"
            for section in index.iter(f"{MALLARD}section")
        }
        for name in page_names():
            if name == "index":
                continue
            root = ET.parse(os.path.join(PAGES, f"{name}.page")).getroot()
            guides = [
                link.get("xref")
                for link in root.find(f"{MALLARD}info")
                if link.tag == f"{MALLARD}link" and link.get("type") == "guide"
            ]
            self.assertEqual(len(guides), 1, name)
            self.assertIn(guides[0], sections, name)


class TestTheFigures(PagesTestCase):
    """The pictures of docs/guide/figures/, which the end-to-end tests take."""

    def figures(self):
        """(page, figure) of each figure of the pages."""

        for name in page_names():
            root = ET.parse(os.path.join(PAGES, f"{name}.page")).getroot()
            for figure in root.iter(f"{MALLARD}figure"):
                yield name, figure

    def test_each_picture_is_shown_once(self):
        shown = sorted(
            media.get("src")
            for _, figure in self.figures()
            for media in figure.iter(f"{MALLARD}media")
        )
        self.assertEqual(
            shown, [f"figures/{name}" for name in picture_names()]
        )

    def test_each_figure_has_a_title_and_a_text(self):
        # the text, for those who don't see the picture
        for page, figure in self.figures():
            self.assertTrue(figure.findtext(f"{MALLARD}title"), page)
            media = figure.find(f"{MALLARD}media")
            self.assertEqual(media.get("type"), "image", page)
            self.assertTrue(media.findtext(f"{MALLARD}p"), page)

    def test_the_html_has_a_copy_of_each(self):
        copies = os.path.join(HTML, "figures")
        self.assertEqual(
            picture_names(),
            sorted(os.listdir(copies)) if os.path.isdir(copies) else [],
            "run python help/build.py",
        )
        for name in picture_names():
            self.assertTrue(
                filecmp.cmp(
                    os.path.join(FIGURES, name),
                    os.path.join(copies, name),
                    shallow=False,
                ),
                name,
            )

    def test_the_pictures_shrink_to_the_window(self):
        # the CSS of help/html.xsl, in the HTML
        with open(os.path.join(HTML, "C.css"), encoding="utf-8") as fp:
            css = fp.read()
        self.assertIn("main > div.page { min-width: 0; }", css)
        self.assertIn("div.media img[data-yelp-original-width]", css)


class TestTheInstall(PagesTestCase):
    """pyproject.toml installs every page, and all of its HTML."""

    def installed(self, folder):
        """
        The files installed in folder: the patterns of its data-files,
        expanded as setuptools does, from the root of the sources.
        """

        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as file:
            project = tomllib.load(file)
        patterns = project["tool"]["setuptools"]["data-files"][folder]
        return sorted(
            os.path.relpath(path, ROOT)
            for pattern in patterns
            for path in glob.glob(os.path.join(ROOT, pattern))
        )

    def test_the_pages_where_yelp_looks(self):
        self.assertEqual(
            self.installed("share/help/C/virtualbricks"),
            [f"docs/built/mallard/{name}.page" for name in page_names()],
        )

    def test_the_html(self):
        # the pages, their style and their scripts
        self.assertEqual(
            self.installed("share/virtualbricks/help/C"),
            [
                f"help/html/C/{name}"
                for name in sorted(os.listdir(HTML))
                if os.path.isfile(os.path.join(HTML, name))
            ],
        )

    def test_the_pictures(self):
        # beside the pages, and beside the HTML
        self.assertEqual(
            self.installed("share/help/C/virtualbricks/figures"),
            [f"docs/built/mallard/figures/{name}" for name in picture_names()],
        )
        self.assertEqual(
            self.installed("share/virtualbricks/help/C/figures"),
            [f"help/html/C/figures/{name}" for name in picture_names()],
        )


class TestYelpCheck(PagesTestCase):
    """The pages against the schema of Mallard, and their links."""

    def setUp(self):
        super().setUp()
        self.yelp_check = shutil.which("yelp-check")
        if self.yelp_check is None:
            raise unittest.SkipTest("yelp-check")

    def check(self, *args):
        # yelp-check is a script of the system's Python: without the
        # PYTHONPATH that trial -j gives its workers, its sys.path
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [self.yelp_check, *args],
            capture_output=True,
            encoding="utf-8",
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_valid(self):
        self.check("validate", *glob.glob(os.path.join(PAGES, "*.page")))

    def test_links(self):
        self.check("links", PAGES)

    def test_no_orphans(self):
        self.assertEqual(self.check("orphans", PAGES), "")


class TestBuild(unittest.TestCase):
    """help/build.py, with yelp-build and yelp-check stood in for."""

    def setUp(self):
        if not os.path.exists(os.path.join(HELP, "build.py")):
            raise unittest.SkipTest("the sources of the guide")
        self.build = load_build()
        self.target = self.mktemp()
        self.patch(self.build, "HTML", self.target)
        self.patch(self.build, "check_pages", lambda: None)
        self.rendered = {"index.html": "index", "C.css": "css"}
        self.patch(self.build, "render", self.render)

    def render(self, folder):
        for name, text in self.rendered.items():
            path = os.path.join(folder, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(text)

    def contents(self):
        result = {}
        for parent, _dirs, names in os.walk(self.target):
            for name in names:
                path = os.path.join(parent, name)
                with open(path, encoding="utf-8") as fp:
                    result[os.path.relpath(path, self.target)] = fp.read()
        return result

    def test_build(self):
        self.assertEqual(self.build.build(), (["C.css", "index.html"], []))
        self.assertEqual(self.contents(), self.rendered)
        # again: nothing to do
        self.assertEqual(self.build.build(), ([], []))

    def test_changed_and_gone(self):
        self.build.build()
        self.rendered = {"index.html": "new index", "first-lab.html": "lab"}
        self.assertEqual(
            self.build.build(), (["first-lab.html", "index.html"], ["C.css"])
        )
        self.assertEqual(self.contents(), self.rendered)

    def test_figures(self):
        """The pictures that yelp-build copies, in figures/."""

        self.rendered["figures/lab.png"] = "picture"
        self.assertEqual(
            self.build.build(),
            (["C.css", "figures/lab.png", "index.html"], []),
        )
        self.assertEqual(self.contents(), self.rendered)
        # gone: the folder too
        del self.rendered["figures/lab.png"]
        self.assertEqual(self.build.build(), ([], ["figures/lab.png"]))
        self.assertEqual(
            sorted(os.listdir(self.target)), ["C.css", "index.html"]
        )

    def test_check_writes_nothing(self):
        self.assertEqual(
            self.build.build(check=True), (["C.css", "index.html"], [])
        )
        self.assertFalse(os.path.exists(self.target))

    def test_main_check(self):
        out = io.StringIO()
        self.patch(sys, "stdout", out)
        self.assertEqual(self.build.main(["--check"]), 1)
        css, index = (
            os.path.relpath(os.path.join(self.target, name), self.build.ROOT)
            for name in ("C.css", "index.html")
        )
        self.assertEqual(
            out.getvalue(),
            f"{css} is out of date\n{index} is out of date\n",
        )
        self.build.build()
        self.assertEqual(self.build.main(["--check"]), 0)

    def test_missing_tool(self):
        # a module of its own, with the real check_pages
        build = load_build()
        self.patch(shutil, "which", lambda name: None)
        err = io.StringIO()
        self.patch(sys, "stderr", err)
        self.assertEqual(build.main([]), 2)
        self.assertEqual(
            err.getvalue(),
            "build.py: yelp-check not found: install yelp-tools\n",
        )
