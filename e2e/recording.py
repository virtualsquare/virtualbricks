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

"""
The screenshot and the video of a scenario, from what broadwayd showed.

The browser of :mod:`broadway` keeps the timeline of the screen: the
surfaces as they are made, their images as broadwayd sends them, and after
each change the surfaces that show and the pointer. Nothing is decoded
while the scenario runs. Replay goes through the timeline afterwards: it
decodes the images as broadway.js does and draws the screen with cairo,
with the pointer and the step of the scenario. ffmpeg makes the video, a
frame for each change.
"""

import os
import shutil
import subprocess
import tempfile
import zlib

import cairo

# A change shows half a second at least: Virtualbricks clicks faster than
# the eye follows.
SHORTEST = 0.5
BACKGROUND = (0.3, 0.3, 0.3)
CAPTION_HEIGHT = 32
CAPTION = (0.15, 0.15, 0.15)
FAILED = (0.7, 0.1, 0.1)


def record(timeline, captions, until, size, folder):
    """
    screenshot.png, the screen at until, and recording.webm, the screen
    until until, in folder; the captions are (time, text, failed). What was
    written, a line for each file.
    """

    events = sorted(
        timeline
        + [(t, "caption", text, failed) for t, text, failed in captions],
        key=lambda event: event[0],
    )
    events = [event for event in events if event[0] <= until]
    lines = []
    path = os.path.join(folder, "screenshot.png")
    replay = Replay(size)
    for event in events:
        replay.apply(event)
    replay.draw().write_to_png(path)
    lines.append(path)
    if shutil.which("ffmpeg") is None:
        lines.append("no video: ffmpeg is not installed")
    elif events:
        path = os.path.join(folder, "recording.webm")
        try:
            _video(events, until, size, path)
            lines.append(path)
        except subprocess.CalledProcessError as error:
            lines.append(f"no video: ffmpeg exited with {error.returncode}")
    return lines


class Replay:
    """The screen, as the events of the timeline happen."""

    def __init__(self, size):
        self.size = size
        # id: (image, width, height), the image in the bytes of cairo's
        # ARGB32, as broadwayd sends it: B, G, R, A
        self.images = {}
        # (id, x, y) of the surfaces that show, bottom first
        self.layout = []
        self.pointer = None
        self.caption = None

    def apply(self, event) -> bool:
        """Apply the event; whether the screen changed."""

        kind = event[1]
        if kind == "surface":
            # a new surface: its first image is not a change of another
            self.images.pop(event[2], None)
            return False
        if kind == "image":
            _, _, id, width, height, compressed = event
            data = zlib.decompress(compressed, -15)
            image = decode(self.images.get(id), width, height, data)
            self.images[id] = (image, width, height)
            return True
        if kind == "layout":
            _, _, layout, pointer = event
            changed = (layout, pointer) != (self.layout, self.pointer)
            self.layout, self.pointer = layout, pointer
            return changed
        if kind == "caption":
            self.caption = event[2:]
            return True
        raise ValueError(f"unknown event {kind!r}")

    def draw(self) -> cairo.ImageSurface:
        width, height = self.size
        screen = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(screen)
        cr.set_source_rgb(*BACKGROUND)
        cr.paint()
        for id, x, y in self.layout:
            if id in self.images:
                data, w, h = self.images[id]
                image = cairo.ImageSurface.create_for_data(
                    data, cairo.FORMAT_ARGB32, w, h, w * 4
                )
                cr.set_source_surface(image, x, y)
                cr.paint()
        if self.pointer is not None:
            cr.arc(*self.pointer, 6, 0, 6.2832)
            cr.set_source_rgba(1, 0, 0, 0.8)
            cr.fill_preserve()
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(1.5)
            cr.stroke()
        if self.caption is not None:
            text, failed = self.caption
            if failed:
                text = f"The step that failed: {text}"
            cr.rectangle(0, height - CAPTION_HEIGHT, width, CAPTION_HEIGHT)
            cr.set_source_rgb(*(FAILED if failed else CAPTION))
            cr.fill()
            cr.select_font_face(
                "sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
            )
            cr.set_font_size(16)
            cr.move_to(12, height - CAPTION_HEIGHT / 2 + 6)
            cr.set_source_rgb(1, 1, 1)
            cr.show_text(text)
        return screen


def decode(old, width, height, data):
    """
    The new image of a surface, width by height: old, (image, width,
    height) or None, changed by data, the inflated buffer of broadwayd.
    decodeBuffer of broadway.js: B, G, R, A words, a pixel if A is not 0,
    else a command in the high nibble of R and a length in the rest of R,
    G and B.
    """

    new = bytearray(width * height * 4)
    target = (new, width, height)
    if old is not None:
        _copy(old, (0, 0), target, (0, 0), old[1:])
    end = len(new)
    src = dest = 0
    while src < len(data):
        if data[src + 3]:
            # pixels, as many as follow
            start = src
            src += 4
            while src < len(data) and data[src + 3]:
                src += 4
            size = max(min(src - start, end - dest), 0)
            new[dest : dest + size] = data[start : start + size]
            dest += src - start
            continue
        b, g, r = data[src : src + 3]
        src += 4
        cmd = r & 0xF0
        length = (r & 0x0F) << 16 | g << 8 | b
        if cmd == 0x00:
            # a transparent pixel
            if dest < end:
                new[dest : dest + 4] = bytes(4)
            dest += 4
        elif cmd == 0x10:
            # pixels as they were
            dest += length * 4
        elif cmd == 0x20:
            # a block of 32 by 32 of the old image, numbered by rows, to
            # the place in the next word
            b, g, r, a = data[src : src + 4]
            src += 4
            if old is not None:
                stride = (old[1] + 31) // 32
                origin = (length % stride * 32, length // stride * 32)
                at = (a << 8 | r, g << 8 | b)
                _copy(old, origin, target, at, (32, 32))
        elif cmd == 0x30:
            # length pixels of a color
            size = max(min(length * 4, end - dest), 0)
            new[dest : dest + size] = data[src : src + 4] * (size // 4)
            src += 4
            dest += length * 4
        elif cmd == 0x40:
            # length pixels, each byte plus that of the word
            delta = data[src : src + 4]
            src += 4
            for i in range(min(length * 4, end - dest)):
                new[dest + i] = (new[dest + i] + delta[i % 4]) & 0xFF
            dest += length * 4
        else:
            raise ValueError(f"unknown command of an image: {cmd:#x}")
    return new


def _copy(source, origin, target, at, size):
    # copyRect of broadway.js: the rectangle of size at origin of source to
    # at of target, both (image, width, height); clipped to both
    src, sw, sh = source
    dst, dw, dh = target
    sx, sy = origin
    dx, dy = at
    width = min(size[0], sw - sx, dw - dx)
    height = min(size[1], sh - sy, dh - dy)
    if width <= 0:
        return
    for row in range(max(height, 0)):
        s = ((sy + row) * sw + sx) * 4
        d = ((dy + row) * dw + dx) * 4
        dst[d : d + width * 4] = src[s : s + width * 4]


def _video(events, until, size, path):
    replay = Replay(size)
    with tempfile.TemporaryDirectory() as folder:
        frames = []
        changed = False
        for event in events:
            changed = replay.apply(event) or changed
            # a frame at the end of each batch of broadwayd, which ends with
            # the layout, and at each step: not for each image of a batch
            if event[1] in ("layout", "caption") and (changed or not frames):
                frame = os.path.join(folder, f"{len(frames):05d}.png")
                replay.draw().write_to_png(frame)
                frames.append((frame, event[0]))
                changed = False
        if not frames:
            frame = os.path.join(folder, "00000.png")
            replay.draw().write_to_png(frame)
            frames.append((frame, events[0][0]))
        # the concat demuxer of ffmpeg: each frame and how long it shows;
        # the last again, briefly, else webm loses its duration, and once
        # more without one
        listing = []
        for i, (frame, at) in enumerate(frames):
            ends = frames[i + 1][1] if i + 1 < len(frames) else until
            shows = max(ends - at, SHORTEST)
            listing += [f"file '{frame}'", f"duration {shows:.3f}"]
        listing += [f"file '{frames[-1][0]}'", "duration 0.040"]
        listing.append(f"file '{frames[-1][0]}'")
        concat = os.path.join(folder, "frames.txt")
        with open(concat, "w") as file:
            file.write("\n".join(listing) + "\n")
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat,
                "-fps_mode",
                "vfr",
                "-c:v",
                "libvpx-vp9",
                "-pix_fmt",
                "yuv420p",
                path,
            ],
            check=True,
        )
