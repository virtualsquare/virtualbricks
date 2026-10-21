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
The user guide: the Mallard pages of docs/built/mallard/ and their HTML in
docs/built/html/, which docs/build.py writes from their Markdown, and their
pictures in docs/guide/figures/.

The tests of the pages are skipped when the sources of the guide are not
there, as in an installed package, and those that run yelp-check when the
Yelp tools are not installed.
"""

import filecmp
import glob
import os
import shutil
import subprocess
import tomllib
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from twisted.trial import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
PAGES = os.path.join(ROOT, "docs", "built", "mallard")
HTML = os.path.join(ROOT, "docs", "built", "html")
FIGURES = os.path.join(ROOT, "docs", "guide", "figures")
MALLARD = "{http://projectmallard.org/1.0/}"


def page_names():
    return sorted(
        os.path.basename(path)[: -len(".page")]
        for path in glob.glob(os.path.join(PAGES, "*.page"))
    )


def picture_names():
    return sorted(os.listdir(FIGURES)) if os.path.isdir(FIGURES) else []


class Links(HTMLParser):
    """The ids of a page of the HTML, and the links and pictures in it."""

    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for name in ("href", "src"):
            if attrs.get(name):
                self.links.append(attrs[name])


def links(name):
    parser = Links()
    with open(os.path.join(HTML, f"{name}.html"), encoding="utf-8") as fp:
        parser.feed(fp.read())
    return parser


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
        self.assertEqual(built, page_names(), "run python docs/build.py")

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


class TestTheReference(PagesTestCase):
    """The man pages, as pages of the guide."""

    def test_a_page_for_each_man_page(self):
        man = os.path.join(ROOT, "docs", "man")
        sources = glob.glob(os.path.join(man, "*.[1-9].md"))
        index = ET.parse(os.path.join(PAGES, "index.page")).getroot()
        self.assertIn(
            "reference",
            [section.get("id") for section in index.iter(f"{MALLARD}section")],
        )
        in_reference = [
            name
            for name in page_names()
            if any(
                link.get("xref") == "index#reference"
                for link in ET.parse(os.path.join(PAGES, f"{name}.page"))
                .getroot()
                .iter(f"{MALLARD}link")
            )
        ]
        self.assertEqual(len(in_reference), len(sources))

    def test_no_link_leaves_yelp(self):
        # the man pages are pages of the guide: Yelp opens no other program
        for name in page_names():
            root = ET.parse(os.path.join(PAGES, f"{name}.page")).getroot()
            for link in root.iter(f"{MALLARD}link"):
                self.assertFalse(
                    (link.get("href") or "").startswith("man:"), name
                )


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
            "run python docs/build.py",
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


class TestTheHtml(PagesTestCase):
    """The HTML of the guide, and of its reference."""

    def test_no_link_leads_nowhere(self):
        pages = {name: links(name) for name in page_names()}
        for name, page in pages.items():
            for target in page.links:
                url = urlsplit(target)
                if url.scheme:
                    # the website, the issues: not of the tree
                    continue
                # a section of the same page, without its path
                path = unquote(url.path) or f"{name}.html"
                path = os.path.normpath(os.path.join(HTML, path))
                self.assertTrue(os.path.isfile(path), f"{name}: {target}")
                if url.fragment:
                    linked = os.path.basename(path)[: -len(".html")]
                    self.assertIn(url.fragment, pages[linked].ids, target)

    def test_every_page_is_in_the_index(self):
        listed = set(links("index").links)
        for name in page_names():
            if name != "index":
                self.assertIn(f"{name}.html", listed)

    def test_its_style(self):
        self.assertIn("style.css", links("index").links)
        self.assertTrue(os.path.isfile(os.path.join(HTML, "style.css")))


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
        # the pages and their style
        self.assertEqual(
            self.installed("share/virtualbricks/help/C"),
            [
                f"docs/built/html/{name}"
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
            [f"docs/built/html/figures/{name}" for name in picture_names()],
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
