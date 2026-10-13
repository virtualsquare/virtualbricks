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
The user guide: the Mallard pages of help/C/ and their HTML in help/html/C/,
which help/build.py makes with the Yelp tools.

The tests of the pages are skipped when the sources of the guide are not
there, as in an installed package, and those that run yelp-check when the
Yelp tools are not installed.
"""

import glob
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from twisted.trial import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
HELP = os.path.join(ROOT, "help")
PAGES = os.path.join(HELP, "C")
HTML = os.path.join(HELP, "html", "C")
MALLARD = "{http://projectmallard.org/1.0/}"


def page_names():
    return sorted(
        os.path.basename(path)[: -len(".page")]
        for path in glob.glob(os.path.join(PAGES, "*.page"))
    )


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


class TestYelpCheck(PagesTestCase):
    """The pages against the schema of Mallard, and their links."""

    def setUp(self):
        super().setUp()
        self.yelp_check = shutil.which("yelp-check")
        if self.yelp_check is None:
            raise unittest.SkipTest("yelp-check")

    def check(self, *args):
        result = subprocess.run(
            [self.yelp_check, *args],
            capture_output=True,
            encoding="utf-8",
            check=False,
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
            with open(os.path.join(folder, name), "w", encoding="utf-8") as fp:
                fp.write(text)

    def contents(self):
        result = {}
        for name in os.listdir(self.target):
            with open(os.path.join(self.target, name), encoding="utf-8") as fp:
                result[name] = fp.read()
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
