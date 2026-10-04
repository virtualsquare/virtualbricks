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

"""A README rendered: its lines, its Pango markup, the label and the view."""

from twisted.internet import defer
from twisted.trial import unittest

from virtualbricks.markdown import parse
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.gui import has_display

if has_display:
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

    from virtualbricks.gui import markdownview
    from virtualbricks.gui.markdownview import (
        INDENT,
        LINE_SEPARATOR,
        MarkdownLabel,
        MarkdownView,
        layout,
        open_link,
        pango_markup,
        read_picture,
    )

README = """\
# OSPF lab

Three routers in a ring, **area 0**, one switch each.
Start the switches before the routers.

## Addresses

- r1: `10.0.1.1/24`
- r2
  1. nested

> Update the others first.

```
vtysh -c 'show ip ospf neighbor'
```

---

Notes: https://bird.network.cz
"""


def lines_of(text):
    return layout(parse(text))


def png(width, height):
    pixbuf = GdkPixbuf.Pixbuf.new(
        GdkPixbuf.Colorspace.RGB, False, 8, width, height
    )
    pixbuf.fill(0x3366CCFF)
    return pixbuf.save_to_bufferv("png", [], [])[1]


class GtkTestCase(unittest.TestCase):

    if not has_display:  # pragma: no cover
        skip = "GTK can't open a display"


class TestLayout(GtkTestCase):

    def test_lines(self):
        self.assertEqual(
            [line.text for line in lines_of("One.\nTwo.\n\nThree.")],
            ["One.", "Two.", "Three."],
        )

    def test_the_space_below_a_block_at_the_top(self):
        lines = lines_of("- a\n- b\n\nOne.\nTwo.\n\n> q\n\nEnd.")
        self.assertEqual(
            [(line.text, "space" in line.styles) for line in lines],
            [
                ("a", False),
                ("b", True),
                ("One.", False),
                ("Two.", True),
                ("q", True),
                ("End.", True),
            ],
        )

    def test_headings(self):
        lines = lines_of("# A\n## B\n### C\n###### F\n\nTitle\n===")
        self.assertEqual(
            [line.styles[0] for line in lines], ["h1", "h2", "h3", "h3", "h1"]
        )

    def test_inline_styles(self):
        [line] = lines_of("*i* **b** ~~s~~ `c` [l](https://a.org) ***ib***")
        runs = [(r.text, set(r.styles), r.href) for r in line.runs]
        self.assertEqual(
            runs,
            [
                ("i", {"em"}, None),
                (" ", set(), None),
                ("b", {"strong"}, None),
                (" ", set(), None),
                ("s", {"strike"}, None),
                (" ", set(), None),
                ("c", {"code"}, None),
                (" ", set(), None),
                ("l", set(), "https://a.org"),
                (" ", set(), None),
                ("ib", {"em", "strong"}, None),
            ],
        )

    def test_links_and_pictures(self):
        [line] = lines_of("see https://a.org, and ![a *map*](m.png)")
        self.assertEqual(
            [(r.text, r.styles, r.href, r.picture) for r in line.runs],
            [
                ("see ", (), None, None),
                ("https://a.org", (), "https://a.org", None),
                (", and ", (), None, None),
                ("a map", ("em",), None, "m.png"),
            ],
        )

    def test_pictures(self):
        [line] = lines_of(
            "![](the%20map.png) ![web](https://a.org/m.png)"
            " [![logo](logo.png)](https://a.org)"
        )
        self.assertEqual(
            [(r.text, r.href, r.picture) for r in line.runs],
            [
                # without a text, its path
                ("the map.png", None, "the map.png"),
                (" ", None, None),
                # not in the folder
                ("web", None, None),
                (" ", None, None),
                ("logo", "https://a.org", "logo.png"),
            ],
        )

    def test_lists(self):
        text = "- a\n- b\n  1. c\n  2. d\n- e\n\n7) x\n8) y\n"
        self.assertEqual(
            [(line.marker, line.depth, line.text) for line in lines_of(text)],
            [
                ("•", 1, "a"),
                ("•", 1, "b"),
                ("1.", 2, "c"),
                ("2.", 2, "d"),
                ("•", 1, "e"),
                ("7)", 1, "x"),
                ("8)", 1, "y"),
            ],
        )

    def test_the_lines_of_an_item(self):
        text = "- first\n  second\n\n  a paragraph\n- next"
        self.assertEqual(
            [(line.marker, line.depth, line.text) for line in lines_of(text)],
            [
                ("•", 1, "first"),
                (None, 1, "second"),
                (None, 1, "a paragraph"),
                ("•", 1, "next"),
            ],
        )

    def test_an_empty_item(self):
        self.assertEqual(
            [(line.marker, line.text) for line in lines_of("-\n- b")],
            [("•", ""), ("•", "b")],
        )

    def test_quotes(self):
        lines = lines_of("> q1\n> q2\n> - item\n\nafter")
        self.assertEqual(
            [
                (line.text, line.depth, "quote" in line.styles)
                for line in lines
            ],
            [("q1", 1, True), ("q2", 1, True), ("item", 2, True)]
            + [("after", 0, False)],
        )

    def test_code_block(self):
        lines = lines_of("```\nx\n  y\n```")
        self.assertEqual(
            [(line.text, line.styles) for line in lines],
            [("x", ("pre",)), ("  y", ("pre", "space"))],
        )

    def test_rule(self):
        lines = lines_of("a\n\n---\n\nb")
        self.assertEqual([line.rule for line in lines], [False, True, False])
        self.assertIn("space", lines[1].styles)


class TestPangoMarkup(GtkTestCase):

    def test_escaped(self):
        self.assertEqual(
            pango_markup("a < b & 'c'"), "a &lt; b &amp; &apos;c&apos;"
        )

    def test_inline(self):
        self.assertEqual(
            pango_markup("*i* **b** ~~s~~ `c` [l](https://a.org/?x=1&y=2)"),
            "<i>i</i> <b>b</b> <s>s</s> <tt>c</tt> "
            '<a href="https://a.org/?x=1&amp;y=2">l</a>',
        )

    def test_lines_and_blocks(self):
        self.assertEqual(
            pango_markup("# Lab\nOne\nTwo\n\n- a\n  1. b\n\n> q"),
            "<b>Lab</b>\n\nOne\nTwo\n\n• a\n  1. b\n\n<i>q</i>",
        )

    def test_a_label_takes_it(self):
        label = Gtk.Label()
        # a label understands <a>, Pango alone doesn't
        label.set_markup(pango_markup(README))
        text = label.get_text()
        self.assertIn("ring, area 0, one", text)
        self.assertIn("Notes: https://bird.network.cz", text)
        self.assertNotIn("<", text)

    def test_pictures_are_their_text(self):
        self.assertEqual(pango_markup("![the map](m.png)"), "<i>the map</i>")
        self.assertEqual(pango_markup("![](m.png)"), "<i>m.png</i>")

    def test_without_links(self):
        self.assertEqual(
            pango_markup("[**BIRD**](https://a.org) and https://b.org", False),
            "<b>BIRD</b> and https://b.org",
        )


class TestReadPicture(GtkTestCase):

    def test_a_picture(self):
        pixbuf = read_picture(png(30, 20))
        self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (30, 20))

    def test_not_a_picture(self):
        self.assertIsNone(read_picture(b"not a picture"))
        self.assertIsNone(read_picture(b""))
        self.assertIsNone(read_picture(png(30, 20)[:40]))

    def test_too_many_pixels(self):
        self.patch(markdownview, "PICTURE_PIXELS", 599)
        self.assertIsNone(read_picture(png(30, 20)))
        self.patch(markdownview, "PICTURE_PIXELS", 600)
        self.assertIsNotNone(read_picture(png(30, 20)))


class TestMarkdownLabel(GtkTestCase):

    # longer than a line of 300 pixels, however wide the font
    LONG = "word " * 60

    def setUp(self):
        # without a window, that would give it a width of its own
        self.label = MarkdownLabel(lines=4, visible=True)
        self.addCleanup(self.label.destroy)

    def allocate(self, width):
        # GTK asks the size first
        self.label.get_preferred_width()
        self.label.get_preferred_height_for_width(width)
        allocation = Gdk.Rectangle()
        allocation.width = width
        allocation.height = 200
        self.label.size_allocate(allocation)

    def fit(self, text, width=400):
        self.label.set_markdown(text)
        self.allocate(width)
        self.label.fit()
        return self.shown()

    def shown(self):
        return self.label.get_label().split(LINE_SEPARATOR)

    def test_the_lines_that_fit(self):
        self.assertEqual(self.fit("One\nTwo"), ["One", "Two"])
        self.assertEqual(
            self.fit("One\nTwo\nThree\nFour"), ["One", "Two", "Three", "Four"]
        )
        self.assertEqual(self.fit(""), [""])

    def test_more_lines_than_room(self):
        self.assertEqual(
            self.fit("One\nTwo\nThree\nFour\nFive\nSix"),
            ["One", "Two", "Three", "Four …"],
        )

    def test_a_long_line_is_the_last(self):
        text = f"One\n{self.LONG}\nThree"
        self.assertEqual(self.fit(text, 300), ["One", self.LONG.strip()])
        # Pango trims it, and the label asks for the room of four lines
        self.allocate(300)
        label_layout = self.label.get_layout()
        self.assertEqual(label_layout.get_line_count(), 4)
        self.assertTrue(label_layout.is_ellipsized())
        _, height = self.label.get_preferred_height_for_width(300)
        self.label.set_markdown("One")
        _, one = self.label.get_preferred_height_for_width(300)
        self.assertEqual(height, 4 * one)
        # the first line takes more than the room: Pango's "…" is enough
        self.assertEqual(
            self.fit(f"{self.LONG}\nTwo", 300), [self.LONG.strip()]
        )

    def test_all_of_it_before_the_width_is_known(self):
        # as high as the lines that fit
        self.label.set_markdown("One\nTwo\nThree\nFour\nFive")
        self.assertEqual(self.shown(), ["One", "Two", "Three", "Four", "Five"])

    def test_another_width(self):
        text = f"One\n{self.LONG}\nThree"
        self.fit(text, 300)
        self.allocate(20000)
        self.label.fit()
        self.assertEqual(self.shown(), ["One", self.LONG.strip(), "Three"])

    def test_another_font(self):
        text = "One\nTwo\nThree\nFour\nFive"
        self.assertEqual(len(self.fit(text, 300)), 4)
        style = Gtk.CssProvider()
        style.load_from_data(b"label { font-size: 200px; }")
        self.label.get_style_context().add_provider(
            style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # as GTK does, for a label in a window
        self.label.emit("style-updated")
        self.allocate(300)
        self.label.fit()
        self.assertLess(len(self.shown()), 4)

    def test_the_fit_waits_for_the_room(self):
        self.label.set_markdown("One\nTwo\nThree\nFour\nFive")
        self.allocate(400)
        # not while GTK gives it its size
        self.assertEqual(len(self.shown()), 5)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertEqual(self.shown(), ["One", "Two", "Three", "Four …"])

    def test_no_fit_after_the_end(self):
        self.label.set_markdown("One\nTwo\nThree\nFour\nFive")
        self.allocate(400)
        self.label.destroy()
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertEqual(len(self.shown()), 5)

    def test_links(self):
        opened = []
        self.patch(
            Gtk,
            "show_uri_on_window",
            lambda window, uri, time: opened.append(uri),
        )
        # measured without links, which Pango alone doesn't know
        self.assertEqual(
            self.fit("[One](https://a.org)\nTwo\nThree\nFour\nFive"),
            ['<a href="https://a.org">One</a>', "Two", "Three", "Four …"],
        )
        self.assertTrue(self.label.emit("activate-link", "https://a.org"))
        self.assertEqual(opened, ["https://a.org"])


class ViewTestCase(GtkTestCase):

    def setUp(self):
        self.window = Gtk.OffscreenWindow()
        self.addCleanup(self.window.destroy)
        self.view = MarkdownView(left_margin=10, right_margin=10)
        self.window.add(self.view)
        self.window.set_default_size(400, 300)
        self.window.show_all()
        self.buffer = self.view.get_buffer()

    def show(self, text, pictures=None):
        self.view.set_markdown(text, pictures)
        self.pump()

    def pump(self):
        for _ in range(20):
            while Gtk.events_pending():
                Gtk.main_iteration()

    def text(self):
        """The text, with a character for each widget in it."""

        start, end = self.buffer.get_bounds()
        return self.buffer.get_slice(start, end, True)

    def iter_at(self, needle):
        offset = self.text().index(needle)
        return self.buffer.get_iter_at_offset(offset)

    def tags_at(self, needle):
        return {tag.props.name for tag in self.iter_at(needle).get_tags()}


class TestMarkdownView(ViewTestCase):

    def test_read_only(self):
        self.assertFalse(self.view.get_editable())
        self.assertFalse(self.view.get_cursor_visible())
        self.assertEqual(self.view.get_wrap_mode(), Gtk.WrapMode.WORD_CHAR)
        other = MarkdownView(wrap_mode=Gtk.WrapMode.NONE)
        self.assertEqual(other.get_wrap_mode(), Gtk.WrapMode.NONE)

    def test_the_styles_look_as_they_say(self):
        table = self.buffer.get_tag_table()
        self.assertEqual(table.lookup("em").props.style, Pango.Style.ITALIC)
        self.assertEqual(
            table.lookup("strong").props.weight, Pango.Weight.BOLD
        )
        self.assertTrue(table.lookup("strike").props.strikethrough)
        self.assertEqual(table.lookup("code").props.family, "monospace")
        self.assertEqual(table.lookup("pre").props.family, "monospace")
        self.assertEqual(
            table.lookup("link").props.underline, Pango.Underline.SINGLE
        )
        scales = [table.lookup(h).props.scale for h in ("h1", "h2", "h3")]
        self.assertEqual(scales, sorted(scales, reverse=True))
        self.assertGreater(scales[-1], 1)

    def test_text(self):
        self.show(README)
        self.assertEqual(
            self.text(),
            "OSPF lab\n"
            "Three routers in a ring, area 0, one switch each.\n"
            "Start the switches before the routers.\n"
            "Addresses\n"
            "• r1: 10.0.1.1/24\n"
            "• r2\n"
            "1. nested\n"
            "Update the others first.\n"
            "vtysh -c 'show ip ospf neighbor'\n"
            # the rule, a separator in the text
            "￼\n" "Notes: https://bird.network.cz",
        )

    def test_styles(self):
        self.show(README)
        self.assertIn("h1", self.tags_at("OSPF lab"))
        self.assertIn("strong", self.tags_at("area 0"))
        self.assertIn("code", self.tags_at("10.0.1.1"))
        self.assertIn("quote", self.tags_at("Update"))
        self.assertIn("pre", self.tags_at("vtysh"))
        self.assertIn("link", self.tags_at("https://bird"))
        self.assertIn("space", self.tags_at("Start the switches"))

    def margin_at(self, needle):
        [name] = [n for n in self.tags_at(needle) if n.startswith("margin:")]
        tag = self.buffer.get_tag_table().lookup(name)
        return tag.props.left_margin, tag.props.indent

    def test_margins(self):
        self.show(README)
        self.assertEqual(self.margin_at("Three"), (10, 0))
        left, indent = self.margin_at("r1:")
        self.assertEqual(left, 10 + INDENT)
        # the bullet hangs before the text: as wide as it
        width = self.view.create_pango_layout("• ").get_pixel_size()[0]
        self.assertEqual(indent, -width)
        self.assertEqual(self.margin_at("nested")[0], 10 + 2 * INDENT)
        self.assertEqual(self.margin_at("Update"), (10 + INDENT, 0))

    def test_links(self):
        self.show("[BIRD](https://bird.network.cz) and https://a.org")
        self.assertEqual(
            self.view.link_at(self.iter_at("BIRD")), "https://bird.network.cz"
        )
        self.assertEqual(
            self.view.link_at(self.iter_at("https://a")), "https://a.org"
        )
        self.assertIsNone(self.view.link_at(self.iter_at("and")))

    def test_links_of_an_old_text_go(self):
        self.show("[a](https://a.org) [b](https://b.org)")
        self.show("[c](https://c.org)")
        self.assertEqual(self.text(), "c")
        table = self.buffer.get_tag_table()
        names = []
        table.foreach(lambda tag, *data: names.append(tag.props.name))
        self.assertEqual(
            [n for n in names if n.startswith("link:")], ["link:0"]
        )
        self.assertEqual(self.view.link_at(self.iter_at("c")), "https://c.org")

    def test_rule(self):
        self.show(README)
        [separator] = self.view.get_children()
        self.assertIsInstance(separator, Gtk.Separator)
        self.assertTrue(separator.get_visible())
        width = self.view.get_allocated_width()
        self.assertEqual(separator.get_size_request()[0], width - 10 - 10)
        allocation = Gdk.Rectangle()
        allocation.width = 600
        self.view.on_size_allocate(self.view, allocation)
        self.assertEqual(separator.get_size_request()[0], 600 - 20)
        # a new text drops it
        self.show("no rule")
        self.assertEqual(self.view.get_children(), [])

    def test_a_rule_follows_the_width(self):
        self.show("a\n\n---\n\nb")
        [separator] = self.view.get_children()
        # the signal of a new width
        allocation = Gdk.Rectangle()
        allocation.width, allocation.height = 500, 300
        self.view.size_allocate(allocation)
        self.assertEqual(separator.get_size_request()[0], 500 - 20)

    def test_a_rule_can_be_seen(self):
        self.show("before\n\n---\n\nafter")
        [separator] = self.view.get_children()
        allocation = separator.get_allocation()
        pixbuf = self.window.get_pixbuf()
        pixels = pixbuf.get_pixels()

        def grey(x, y):
            at = y * pixbuf.get_rowstride() + x * pixbuf.get_n_channels()
            return sum(pixels[at : at + 3]) / 3

        x = allocation.x + 20
        rule = grey(x, allocation.y)
        background = grey(x, allocation.y - 3)
        # the separator of a theme is almost the colour of the background
        self.assertGreater(abs(background - rule), 40)

    def test_iter_at(self):
        self.show("[BIRD](https://bird.network.cz) and more")
        it = self.iter_at("more")
        rect = self.view.get_iter_location(it)
        x, y = self.view.buffer_to_window_coords(
            Gtk.TextWindowType.TEXT, rect.x + 1, rect.y + 1
        )
        self.assertEqual(
            self.view._iter_at(x, y).get_offset(), it.get_offset()
        )
        # below the text, nothing
        self.assertIsNone(self.view._iter_at(x, 1000))

    def test_the_signals(self):
        calls = []

        def handler(name):
            def handle(view, *args):
                calls.append(name)
                # nothing else sees the events made here
                return True

            return handle

        self.patch(MarkdownView, "on_button_release_event", handler("click"))
        self.patch(MarkdownView, "on_motion_notify_event", handler("motion"))
        view = MarkdownView()
        view.emit(
            "button-release-event",
            Gdk.Event.new(Gdk.EventType.BUTTON_RELEASE),
        )
        view.emit(
            "motion-notify-event", Gdk.Event.new(Gdk.EventType.MOTION_NOTIFY)
        )
        self.assertEqual(calls, ["click", "motion"])

    def test_colors_from_the_theme(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(b"textview, textview text { color: #ff0000; }")
        context = self.view.get_style_context()
        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.view.update_colors()
        table = self.buffer.get_tag_table()
        quote = table.lookup("quote").props.foreground_rgba
        self.assertEqual(
            (quote.red, quote.green, quote.blue, quote.alpha), (1, 0, 0, 0.6)
        )
        tint = table.lookup("pre").props.paragraph_background_rgba
        self.assertEqual((tint.red, tint.alpha), (1, 0.08))
        link = table.lookup("link").props.foreground_rgba
        self.assertTrue(link.equal(context.get_color(Gtk.StateFlags.LINK)))

    def test_colors_follow_a_change_of_theme(self):
        updates = []
        self.patch(
            MarkdownView, "update_colors", lambda view: updates.append(1)
        )
        self.view.emit("style-updated")
        self.assertEqual(updates, [1])


class TestPictures(ViewTestCase):

    def setUp(self):
        super().setUp()
        self.asked = []
        self.files = {"map.png": png(40, 30), "wide.png": png(1000, 100)}

    def pictures(self, path):
        self.asked.append(path)
        if path not in self.files:
            return defer.fail(FileNotFoundError(path))
        return defer.succeed(self.files[path])

    def images(self):
        return [
            child
            for child in self.view.get_children()
            if isinstance(child, Gtk.Image)
        ]

    def test_a_picture_takes_the_place_of_its_text(self):
        self.show("Map: ![the map](map.png) here", self.pictures)
        self.assertEqual(self.asked, ["map.png"])
        self.assertEqual(self.text(), "Map: \ufffc here")
        [image] = self.images()
        self.assertTrue(image.get_visible())
        pixbuf = image.get_pixbuf()
        self.assertEqual((pixbuf.get_width(), pixbuf.get_height()), (40, 30))
        # what a screen reader says
        self.assertEqual(image.get_accessible().get_name(), "the map")

    def test_the_tags_of_its_text(self):
        self.show("- [![logo](map.png)](https://a.org) **b**", self.pictures)
        self.assertEqual(self.text(), "• \ufffc b")
        at = self.iter_at("\ufffc")
        self.assertEqual(self.view.link_at(at), "https://a.org")
        names = {tag.props.name for tag in at.get_tags()}
        self.assertIn("em", names)
        self.assertEqual(names & {"strong"}, set())
        self.assertTrue(any(name.startswith("margin:") for name in names))

    def test_only_the_pictures_of_the_folder_are_asked_for(self):
        self.show(
            "![a](https://a.org/a.png) ![b](/etc/b.png) ![c](map.png)",
            self.pictures,
        )
        self.assertEqual(self.asked, ["map.png"])
        self.assertEqual(self.text(), "a b \ufffc")

    def test_without_pictures(self):
        self.show("![the map](map.png)")
        self.assertEqual(self.text(), "the map")
        self.assertEqual(self.images(), [])

    def test_a_picture_that_doesnt_come(self):
        self.show("![the map](gone.png) and ![](gone.png)", self.pictures)
        self.assertEqual(self.text(), "the map and gone.png")
        self.assertEqual(self.images(), [])

    def test_not_a_picture(self):
        self.files["map.png"] = b"not a picture"
        self.show("![the map](map.png)", self.pictures)
        self.assertEqual(self.text(), "the map")
        self.assertEqual(self.images(), [])

    def test_pictures_that_come_later(self):
        coming = []

        def later(path):
            coming.append(defer.Deferred())
            return coming[-1]

        self.show("![one](map.png) ![two](map.png)", later)
        self.assertEqual(self.text(), "one two")
        coming[1].callback(png(40, 30))
        self.pump()
        self.assertEqual(self.text(), "one \ufffc")
        # the other picture didn't move it
        coming[0].callback(png(40, 30))
        self.pump()
        self.assertEqual(self.text(), "\ufffc \ufffc")
        self.assertEqual(len(self.images()), 2)

    def test_a_picture_of_another_readme(self):
        coming = defer.Deferred()
        self.show("![one](map.png)", lambda path: coming)
        self.show("Another ![two](map.png)")
        coming.callback(png(40, 30))
        self.pump()
        self.assertEqual(self.text(), "Another two")
        self.assertEqual(self.images(), [])

    def test_a_new_readme_drops_the_pictures(self):
        self.show("![one](map.png)", self.pictures)
        [image] = self.images()
        self.show("none")
        self.assertEqual(self.images(), [])
        self.assertIsNone(image.get_parent())

    def shown_width(self):
        [image] = self.images()
        return image.get_pixbuf().get_width()

    def test_as_wide_as_the_view(self):
        self.show("![wide](wide.png)", self.pictures)
        width = self.view.get_allocated_width()
        self.assertGreater(width, 1)
        # the margins of the view
        self.assertEqual(self.shown_width(), width - 10 - 10)
        [image] = self.images()
        self.assertEqual(
            image.get_pixbuf().get_height(), round(100 * (width - 20) / 1000)
        )
        # in a list, the room is less
        self.show("- ![wide](wide.png)", self.pictures)
        self.assertEqual(self.shown_width(), width - 10 - INDENT - 10)

    def test_never_wider_than_it_is(self):
        self.show("![the map](map.png)", self.pictures)
        self.assertEqual(self.shown_width(), 40)

    def test_another_width(self):
        self.show("![wide](wide.png)", self.pictures)
        allocation = Gdk.Rectangle()
        allocation.width, allocation.height = 500, 300
        self.view.size_allocate(allocation)
        # once GTK is done with the sizes
        self.assertIsNotNone(self.view._fitting)
        self.view._fit_later()
        self.assertIsNone(self.view._fitting)
        self.assertEqual(self.shown_width(), 500 - 20)

    def test_a_picture_before_the_view_has_its_width(self):
        view = MarkdownView(visible=True)
        self.addCleanup(view.destroy)
        view.set_markdown("![wide](wide.png)", self.pictures)
        [image] = [c for c in view.get_children() if isinstance(c, Gtk.Image)]
        self.assertIsNone(image.get_pixbuf())
        # GTK asks the size first
        view.get_preferred_width()
        view.get_preferred_height_for_width(300)
        allocation = Gdk.Rectangle()
        allocation.width, allocation.height = 300, 200
        view.size_allocate(allocation)
        view._fit_later()
        self.assertEqual(image.get_pixbuf().get_width(), 300)

    def test_its_line_is_measured_again(self):
        table = self.buffer.get_tag_table()
        self.assertTrue(table.lookup("picture").props.rise_set)
        self.assertEqual(table.lookup("picture").props.rise, 0)
        self.show("![wide](wide.png)", self.pictures)
        self.assertIn("picture", self.tags_at("\ufffc"))
        changes = []

        def changed(change):
            def record(textbuffer, tag, start, end):
                changes.append((change, tag.props.name, start.get_offset()))

            return record

        self.buffer.connect("remove-tag", changed("off"))
        self.buffer.connect("apply-tag", changed("on"))
        allocation = Gdk.Rectangle()
        allocation.width, allocation.height = 500, 300
        self.view.size_allocate(allocation)
        self.view._fit_later()
        # a tag of the size comes and goes
        self.assertEqual(
            changes, [("off", "picture", 0), ("on", "picture", 0)]
        )
        # the same width: nothing to measure
        self.view._fit_later()
        self.assertEqual(len(changes), 2)

    def test_the_view_asks_for_its_size_again(self):
        self.show("![the map](map.png)", self.pictures)
        resized = []
        self.patch(self.view, "queue_resize", lambda: resized.append(True))
        self.assertEqual(resized, [])
        # GTK's own idle calls first
        self.view.set_markdown("![wide](wide.png)", self.pictures)
        self.assertIsNotNone(self.view._resizing)
        self.view._resize_later()
        self.assertEqual(resized, [True])
        self.assertIsNone(self.view._resizing)

    def test_no_fit_after_the_end(self):
        self.show("![wide](wide.png)", self.pictures)
        allocation = Gdk.Rectangle()
        allocation.width, allocation.height = 500, 300
        self.view.size_allocate(allocation)
        fitting = self.view._fitting
        self.assertIsNotNone(fitting)
        self.view._size_picture(self.view._pictures[0], 300)
        resizing = self.view._resizing
        self.assertIsNotNone(resizing)
        self.view.destroy()
        self.assertIsNone(self.view._fitting)
        self.assertIsNone(self.view._resizing)
        context = GLib.main_context_default()
        self.assertIsNone(context.find_source_by_id(fitting))
        self.assertIsNone(context.find_source_by_id(resizing))


class FakeEvent:
    def __init__(self, button=1, x=0, y=0):
        self.button = button
        self.x = x
        self.y = y


class TestOpeningLinks(ViewTestCase):

    def setUp(self):
        super().setUp()
        self.opened = []
        self.patch(
            Gtk,
            "show_uri_on_window",
            lambda window, uri, time: self.opened.append((window, uri)),
        )

    def test_the_schemes_that_open(self):
        for uri in ("https://a.org", "http://a.org", "mailto:a@b.org"):
            self.assertTrue(open_link(self.view, uri))
        for uri in ("file:///etc/passwd", "notes.txt", "ftp://a.org", ""):
            # handled: a label doesn't open it either
            self.assertTrue(open_link(self.view, uri))
        self.assertEqual(
            [uri for _, uri in self.opened],
            ["https://a.org", "http://a.org", "mailto:a@b.org"],
        )
        # the window of the view
        self.assertIs(self.opened[0][0], self.window)

    def test_an_error(self):
        logger = FakeLogger()
        self.patch(markdownview, "logger", logger)

        def fail(window, uri, time):
            raise GLib.Error("no browser")

        self.patch(Gtk, "show_uri_on_window", fail)
        self.assertTrue(open_link(self.view, "https://a.org"))
        self.assertEqual(
            logger.formatted(), ["Cannot open https://a.org: no browser"]
        )

    def test_a_click(self):
        self.show("[BIRD](https://bird.network.cz) and more")
        at = {"it": self.iter_at("BIRD")}
        self.patch(self.view, "_iter_at", lambda x, y: at["it"])
        self.assertTrue(
            self.view.on_button_release_event(self.view, FakeEvent())
        )
        self.assertEqual(
            [uri for _, uri in self.opened], ["https://bird.network.cz"]
        )
        # not on a link, not the first button, or selecting
        at["it"] = self.iter_at("more")
        self.assertFalse(
            self.view.on_button_release_event(self.view, FakeEvent())
        )
        at["it"] = self.iter_at("BIRD")
        self.assertFalse(
            self.view.on_button_release_event(self.view, FakeEvent(button=3))
        )
        start, end = self.buffer.get_bounds()
        self.buffer.select_range(start, end)
        self.assertFalse(
            self.view.on_button_release_event(self.view, FakeEvent())
        )
        self.assertEqual(len(self.opened), 1)

    def test_the_pointer_over_a_link(self):
        self.show("[BIRD](https://bird.network.cz) and more")
        cursors = []
        # a cursor of GTK 3 doesn't tell its name
        self.patch(Gdk.Cursor, "new_from_name", lambda display, name: name)
        window = self.view.get_window(Gtk.TextWindowType.TEXT)
        self.patch(window, "set_cursor", cursors.append)
        at = {"it": self.iter_at("BIRD")}
        self.patch(self.view, "_iter_at", lambda x, y: at["it"])
        # GTK goes on with the event, to select text
        self.assertFalse(
            self.view.on_motion_notify_event(self.view, FakeEvent())
        )
        self.view.on_motion_notify_event(self.view, FakeEvent())
        at["it"] = self.iter_at("more")
        self.view.on_motion_notify_event(self.view, FakeEvent())
        self.assertEqual(cursors, ["pointer", "text"])
