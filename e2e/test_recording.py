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

"""The tests of recording.py: the images of broadwayd, decoded and drawn."""

import os
import shutil
import subprocess
import zlib

import cairo
import pytest

import recording

# pixels as broadwayd sends them: B, G, R, A
RED = bytes([0, 0, 255, 255])
GREEN = bytes([0, 255, 0, 255])
BLUE = bytes([255, 0, 0, 255])


def command(cmd, length):
    """A word of a command: its length in B, G and the low nibble of R."""

    return bytes([length & 0xFF, length >> 8 & 0xFF, cmd | length >> 16, 0])


def place(x, y):
    """The word after a block reference: where the block goes."""

    return bytes([y & 0xFF, y >> 8, x & 0xFF, x >> 8])


def pixel(image, width, x, y):
    start = (y * width + x) * 4
    return bytes(image[start : start + 4])


def image(at, id, width, height, data):
    """The event of an image, deflated as broadwayd sends it."""

    deflate = zlib.compressobj(wbits=-15)
    compressed = deflate.compress(data) + deflate.flush()
    return (at, "image", id, width, height, compressed)


def screen_pixel(screen, x, y):
    screen.flush()
    return pixel(screen.get_data(), screen.get_width(), x, y)


# decode: the commands of decodeBuffer


def test_pixels():
    assert recording.decode(None, 2, 1, RED + GREEN) == RED + GREEN


def test_transparent():
    old = (bytearray(RED * 2), 2, 1)
    data = command(0x00, 0) + GREEN
    assert recording.decode(old, 2, 1, data) == bytes(4) + GREEN


def test_unchanged_run():
    old = (bytearray(RED + GREEN + BLUE), 3, 1)
    data = command(0x10, 2) + GREEN
    assert recording.decode(old, 3, 1, data) == RED + GREEN + GREEN


def test_block():
    """Block 1 of an image 64 wide is the second of the first row."""

    old = bytearray()
    for _ in range(32):
        old += RED * 32 + BLUE * 32
    new = recording.decode(
        (old, 64, 32), 64, 32, command(0x20, 1) + place(0, 0)
    )
    assert pixel(new, 64, 0, 0) == BLUE
    assert pixel(new, 64, 31, 31) == BLUE
    assert pixel(new, 64, 32, 0) == BLUE


def test_color_run():
    assert recording.decode(None, 3, 1, command(0x30, 3) + GREEN) == GREEN * 3


def test_delta_run():
    """Each byte plus that of the word, modulo 256."""

    old = (bytearray([250, 10, 20, 255]), 1, 1)
    data = command(0x40, 1) + bytes([10, 1, 2, 0])
    assert recording.decode(old, 1, 1, data) == bytes([4, 11, 22, 255])


def test_larger():
    """A surface grown: the old image is where it was."""

    old = (bytearray(RED), 1, 1)
    data = command(0x10, 1) + GREEN
    assert recording.decode(old, 2, 1, data) == RED + GREEN


def test_unknown_command():
    with pytest.raises(ValueError):
        recording.decode(None, 1, 1, command(0x50, 0))


# Replay


def test_stacking():
    """The surfaces at their place, the last on top."""

    replay = recording.Replay((8, 8))
    replay.apply(image(0, 1, 2, 2, RED * 4))
    replay.apply(image(0, 2, 1, 1, GREEN))
    replay.apply((0, "layout", [(1, 0, 0), (2, 1, 1)], None))
    screen = replay.draw()
    empty = recording.Replay((8, 8)).draw()
    assert screen_pixel(screen, 0, 0) == RED
    assert screen_pixel(screen, 1, 1) == GREEN
    assert screen_pixel(screen, 5, 5) == screen_pixel(empty, 5, 5)


def test_new_surface():
    """A surface made again with an id: its image starts over."""

    replay = recording.Replay((4, 4))
    replay.apply(image(0, 1, 1, 1, RED))
    replay.apply((1, "surface", 1))
    replay.apply(image(1, 1, 1, 1, command(0x10, 1)))
    assert bytes(replay.images[1][0]) == bytes(4)


def test_layout_unchanged():
    replay = recording.Replay((4, 4))
    assert replay.apply((0, "layout", [(1, 0, 0)], (1, 1)))
    assert not replay.apply((1, "layout", [(1, 0, 0)], (1, 1)))
    assert replay.apply((2, "layout", [(1, 0, 0)], (2, 1)))


def test_caption_failed():
    """The band of the step is red when the step failed."""

    replay = recording.Replay((100, 50))
    replay.apply((0, "caption", "Then sw1 is running", False))
    b, g, r, _ = screen_pixel(replay.draw(), 99, 49)
    assert r < 100
    replay.apply((1, "caption", "Then sw1 is running", True))
    b, g, r, _ = screen_pixel(replay.draw(), 99, 49)
    assert r > 150 and g < 50 and b < 50


# record


def timeline():
    """A surface red at 0, green at 3."""

    return [
        (0, "surface", 1),
        image(0, 1, 2, 2, RED * 4),
        (0, "layout", [(1, 0, 0)], None),
        image(3, 1, 2, 2, GREEN * 4),
        (3, "layout", [(1, 0, 0)], None),
    ]


def test_screenshot_until(tmp_path):
    """The screenshot is the screen at until, not after."""

    lines = recording.record(timeline(), [], 2, (8, 8), str(tmp_path))
    assert lines[0] == str(tmp_path / "screenshot.png")
    screen = cairo.ImageSurface.create_from_png(lines[0])
    assert screen_pixel(screen, 0, 0) == RED


def test_without_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(recording.shutil, "which", lambda name: None)
    lines = recording.record(timeline(), [], 5, (8, 8), str(tmp_path))
    assert lines[1] == "no video: ffmpeg is not installed"
    assert not os.path.exists(tmp_path / "recording.webm")


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="not installed: ffmpeg",
)
def test_video_length(tmp_path):
    """
    A change shows half a second at least, the last until until: red 0.1 s,
    shown 0.5 s, then green 2.9 s, and 0.04 s that keeps the length.
    """

    events = [
        image(0, 1, 2, 2, RED * 4),
        (0, "layout", [(1, 0, 0)], None),
        image(0.1, 1, 2, 2, GREEN * 4),
        (0.1, "layout", [(1, 0, 0)], None),
    ]
    lines = recording.record(events, [], 3, (8, 8), str(tmp_path))
    assert lines[1] == str(tmp_path / "recording.webm")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            lines[1],
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(probe.stdout) == pytest.approx(3.44, abs=0.1)
