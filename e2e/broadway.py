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
The screen and the mouse of the end-to-end tests: broadwayd, the display
server of GTK's HTML5 backend, and a browser of our own.

broadwayd shows the windows to a browser over a WebSocket: it tells it of
each surface (a window, a menu, a tooltip) as it is made, moved, shown,
raised, hidden. The browser sends back the pointer and the keys. Browser is
that browser, without a page: it keeps the surfaces, and its clicks reach
GTK through broadwayd as a user's would, onto whatever is shown there.

It speaks the protocol of the browser client of GTK 3.24, broadway.js, in
broadwayd: what it sends, and when, is what broadway.js does.

It doesn't draw: it keeps the timeline of the screen, the images of the
surfaces as broadwayd sends them and, after each change, the surfaces that
show and the pointer. :mod:`recording` makes a screenshot and a video of
it.
"""

import base64
import os
import socket
import struct
import threading
import time

# The size of the screen, which the browser tells broadwayd.
SCREEN = (1280, 1024)
GDK_CROSSING_NORMAL = 0
GDK_CROSSING_GRAB = 1
GDK_CROSSING_UNGRAB = 2
GDK_SHIFT_MASK = 1 << 0
GDK_CONTROL_MASK = 1 << 2
GDK_MOD1_MASK = 1 << 3
GDK_BUTTON1_MASK = 1 << 8
# A click comes this long after the one before at least: more than
# gtk-double-click-time (400 ms), so that GTK never takes two clicks for a
# double click.
CLICK_WAIT = 0.5
# The moves of a drag, between its press and its release.
DRAG_STEPS = 10
# The keysyms of the keys by name, those that aren't a character; a
# modifier is its left key, with the mask it adds to the state.
KEYSYMS = {
    "BackSpace": 0xFF08,
    "Tab": 0xFF09,
    "Return": 0xFF0D,
    "Escape": 0xFF1B,
    "Delete": 0xFFFF,
    "F2": 0xFFBF,
    "Shift": 0xFFE1,
    "Control": 0xFFE3,
    "Alt": 0xFFE9,
}
MODIFIERS = {
    "Shift": GDK_SHIFT_MASK,
    "Control": GDK_CONTROL_MASK,
    "Alt": GDK_MOD1_MASK,
}


class Surface:
    """A window, as the browser knows it."""

    def __init__(self, id, x, y, width, height, temp):
        self.id = id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.temp = temp
        self.visible = False
        self.parent = 0

    def holds(self, x, y) -> bool:
        return (
            self.visible
            and self.x <= x < self.x + self.width
            and self.y <= y < self.y + self.height
        )


class Browser:
    """
    The browser of a broadwayd that listens on the Unix socket path, with
    the pointer.
    """

    def __init__(self, path, timeout=10.0):
        self.surfaces = {}
        # bottom first
        self.stacking = []
        self.serial = 0
        self.state = 0
        self.x = self.y = 0
        # moved once: a video shows the pointer from then on
        self.pointed = False
        # when the last press was, or None
        self.pressed = None
        # realWindowWithMouse and windowWithMouse of broadway.js
        self.real_under = 0
        self.under = 0
        # (surface, owner events, implicit)
        self.grab = None
        self.closed = False
        self.changed = threading.Condition()
        # (time, kind, ...): "surface", id; "image", id, width, height,
        # deflated data; "layout", [(id, x, y)] bottom first, pointer
        self.timeline = []
        self._sending = threading.Lock()
        self._start = time.monotonic()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(path)
        self._handshake()
        self.sock.settimeout(None)
        self._reader = threading.Thread(
            target=self._read, name="broadway", daemon=True
        )
        self._reader.start()
        self.send("d", *SCREEN)

    def close(self):
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        self._reader.join(5)
        # nothing shows any more
        self.timeline.append((time.monotonic(), "layout", [], None))

    # The pointer

    def click(self, x, y, button=1):
        """
        A press and a release of button at x, y of the screen, CLICK_WAIT
        after the last press at least.
        """

        self.press(x, y, button)
        self.release(button)

    def drag(self, start, end, button=1, ready=None):
        """
        A press of button at start, x and y of the screen, moves to end in
        DRAG_STEPS, and a release there: the surface pressed has the
        pointer until the release. ready(), if given, comes right before
        the press, CLICK_WAIT after the press before.
        """

        (x0, y0), (x1, y1) = start, end
        self.pace()
        if ready is not None:
            ready()
        self.press(x0, y0, button)
        for step in range(1, DRAG_STEPS + 1):
            self.move(
                x0 + (x1 - x0) * step // DRAG_STEPS,
                y0 + (y1 - y0) * step // DRAG_STEPS,
            )
        self.release(button)

    def press(self, x, y, button=1):
        """
        A press of button at x, y of the screen, CLICK_WAIT after the last
        press at least: the surface there has the pointer until the release.
        """

        # GTK counts a press on a widget within 400 ms and 5 px of the one
        # before on it as the second of a double click, and the list of New
        # Brick activates a row on the first press only. "When I add the
        # switch sw1" then "When I add the switch sw2" clicked the row
        # Switch twice at the same pixel, 320 ms apart, as the popover opens
        # again on the kind made last: the list only selected the row, and
        # sw2 was never made.
        self.pace()
        self.move(x, y)
        with self.changed:
            self.state |= GDK_BUTTON1_MASK << (button - 1)
            target = self._target(self.real_under)
            if self.grab is None:
                self._grab(target, False, True)
            self.pressed = time.monotonic()
            self._pointer("b", target, button)

    def pace(self):
        """Wait until CLICK_WAIT after the last press."""

        if self.pressed is not None:
            time.sleep(max(self.pressed + CLICK_WAIT - time.monotonic(), 0))

    def release(self, button=1):
        """A release of button where the pointer is."""

        with self.changed:
            self.state &= ~(GDK_BUTTON1_MASK << (button - 1))
            self._pointer("B", self._target(self.real_under), button)
            if self.grab is not None and self.grab[2]:
                self._ungrab()

    def key(self, keys):
        """
        A press and a release of keys, as "Escape", "Return" or
        "Control+l": the modifiers before the last key, held while it is
        pressed. broadwayd gives them to the surface it focused: the one
        pressed last, or the one that GTK asked to focus.
        """

        *modifiers, last = keys.split("+")
        keysym = KEYSYMS[last] if last in KEYSYMS else ord(last)
        with self.changed:
            # as broadway.js: the state of a modifier has it already
            for name in modifiers:
                self.state |= MODIFIERS[name]
                self.send("k", KEYSYMS[name], self.state)
            self.send("k", keysym, self.state)
            self.send("K", keysym, self.state)
            for name in reversed(modifiers):
                self.state &= ~MODIFIERS[name]
                self.send("K", KEYSYMS[name], self.state)

    def scroll(self, x, y, down=True):
        """A turn of the wheel at x, y of the screen, down or up."""

        self.move(x, y)
        with self.changed:
            # onMouseWheel: to the surface under the pointer, grab or not
            self._pointer("s", self.real_under, 1 if down else 0)

    def move(self, x, y):
        """The pointer goes to x, y: it leaves a surface for another."""

        with self.changed:
            self.x, self.y = x, y
            self.pointed = True
            surface = self.surface_at(x, y)
            if surface != self.real_under:
                # mouseout, then mouseover
                target = self._target(self.real_under)
                if target != 0:
                    self._pointer("l", target, GDK_CROSSING_NORMAL)
                self.real_under = surface
                self.under = self._target(surface)
                if self.under != 0:
                    self._pointer("e", self.under, GDK_CROSSING_NORMAL)
            self._pointer("m", self._target(surface))
            self._snapshot()

    def surface_at(self, x, y) -> int:
        """The surface on top at x, y, or 0."""

        with self.changed:
            for surface in reversed(self.stacking):
                if surface.holds(x, y):
                    return surface.id
        return 0

    def _target(self, id):
        # getEffectiveEventTarget
        if self.grab is not None and (not self.grab[1] or id == 0):
            return self.grab[0]
        return id

    def _pointer(self, cmd, target, *more):
        winx, winy = self.x, self.y
        if target in self.surfaces:
            winx -= self.surfaces[target].x
            winy -= self.surfaces[target].y
        self.send(
            cmd,
            self.real_under,
            target,
            self.x,
            self.y,
            winx,
            winy,
            self.state,
            *more,
        )

    def _grab(self, id, owner_events, implicit):
        if self.under != id:
            if self.under != 0:
                self._pointer("l", self.under, GDK_CROSSING_GRAB)
            self._pointer("e", id, GDK_CROSSING_GRAB)
            self.under = id
        self.grab = (id, owner_events, implicit)

    def _ungrab(self):
        if self.real_under != self.under:
            if self.under != 0:
                self._pointer("l", self.under, GDK_CROSSING_UNGRAB)
            if self.real_under != 0:
                self._pointer("e", self.real_under, GDK_CROSSING_UNGRAB)
            self.under = self.real_under
        self.grab = None

    # The WebSocket

    def send(self, cmd, *args):
        """An input message: big-endian 32 bits integers."""

        stamp = int((time.monotonic() - self._start) * 1000)
        words = (ord(cmd), self.serial, stamp) + args
        self._frame(struct.pack(f">{len(words)}i", *words))

    def _frame(self, payload, opcode=2):
        # a client masks what it sends
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            head = struct.pack("!BB", 0x80 | opcode, 0x80 | length)
        elif length < 1 << 16:
            head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, length)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, length)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._sending:
            self.sock.sendall(head + mask + masked)

    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET /socket HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: broadway\r\n"
            "Origin: http://localhost\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        head = b""
        while b"\r\n\r\n" not in head:
            data = self.sock.recv(1)
            if not data:
                raise ConnectionError("broadwayd closed the WebSocket")
            head += data
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise ConnectionError(f"broadwayd answered {status!r}")

    def _recv(self, size):
        data = b""
        while len(data) < size:
            more = self.sock.recv(size - len(data))
            if not more:
                raise EOFError
            data += more
        return data

    def _read(self):
        message = b""
        try:
            while not self.closed:
                first, second = self._recv(2)
                opcode = first & 0x0F
                length = second & 0x7F
                if length == 126:
                    (length,) = struct.unpack("!H", self._recv(2))
                elif length == 127:
                    (length,) = struct.unpack("!Q", self._recv(8))
                mask = self._recv(4) if second & 0x80 else None
                payload = self._recv(length)
                if mask:
                    payload = bytes(
                        b ^ mask[i % 4] for i, b in enumerate(payload)
                    )
                if opcode == 8:
                    break
                if opcode == 9:
                    self._frame(payload, opcode=10)
                    continue
                message += payload
                if first & 0x80 and opcode in (0, 1, 2):
                    with self.changed:
                        self._commands(message)
                        self._snapshot()
                        self.changed.notify_all()
                    message = b""
        except (EOFError, OSError):
            pass
        with self.changed:
            self.closed = True
            self.changed.notify_all()

    # What broadwayd says: handleCommands of broadway.js

    def _commands(self, data):
        pos = 0
        while pos < len(data):
            op = chr(data[pos])
            (self.serial,) = struct.unpack_from("<I", data, pos + 1)
            pos += 5
            if op == "s":
                id, x, y, w, h, temp = struct.unpack_from("<HhhHHB", data, pos)
                pos += 11
                surface = Surface(id, x, y, w, h, bool(temp))
                self.timeline.append((time.monotonic(), "surface", id))
                self.surfaces[id] = surface
                self.stacking.append(surface)
                self._configured(surface)
            elif op in "SHdrR":
                (id,) = struct.unpack_from("<H", data, pos)
                pos += 2
                self._surface_op(op, self.surfaces.get(id))
            elif op == "p":
                id, parent = struct.unpack_from("<HH", data, pos)
                pos += 4
                surface = self.surfaces.get(id)
                if surface is not None and surface.parent != parent:
                    surface.parent = parent
                    if parent in self.surfaces:
                        above = self.stacking.index(self.surfaces[parent])
                        self._move_to(surface, above + 1)
            elif op == "m":
                id, flags = struct.unpack_from("<HB", data, pos)
                pos += 3
                surface = self.surfaces[id]
                if flags & 1:
                    surface.x, surface.y = struct.unpack_from("<hh", data, pos)
                    pos += 4
                if flags & 2:
                    size = struct.unpack_from("<HH", data, pos)
                    surface.width, surface.height = size
                    pos += 4
                self._configured(surface)
            elif op == "b":
                id, w, h, size = struct.unpack_from("<HHHI", data, pos)
                pos += 10
                image = data[pos : pos + size]
                self.timeline.append(
                    (time.monotonic(), "image", id, w, h, image)
                )
                pos += size
            elif op == "g":
                id, owner_events = struct.unpack_from("<HB", data, pos)
                pos += 3
                self._grab(id, bool(owner_events), False)
                self.send("g")
            elif op == "u":
                self.send("u")
                if self.grab is not None:
                    self._ungrab()
            elif op == "k":
                pos += 2
            elif op == "D":
                self.closed = True
            else:
                raise ValueError(f"broadwayd sent the unknown op {op!r}")

    def _snapshot(self):
        layout = [(s.id, s.x, s.y) for s in self.stacking if s.visible]
        pointer = (self.x, self.y) if self.pointed else None
        self.timeline.append((time.monotonic(), "layout", layout, pointer))

    def _surface_op(self, op, surface):
        if surface is None:
            return
        if op == "S":
            surface.visible = True
        elif op in "Hd":
            if self.grab is not None and self.grab[0] == surface.id:
                self._ungrab()
            surface.visible = False
            if op == "d":
                self.stacking.remove(surface)
                del self.surfaces[surface.id]
                if self.under == surface.id:
                    self.under = 0
                if self.real_under == surface.id:
                    self.real_under = 0
        elif op == "r":
            self._move_to(surface, None)
        elif op == "R":
            self._move_to(surface, 0)

    def _move_to(self, surface, position):
        # moveToHelper: the transient surfaces follow
        self.stacking.remove(surface)
        if position is None:
            self.stacking.append(surface)
        else:
            self.stacking.insert(position, surface)
        for child in list(self.surfaces.values()):
            if child.parent == surface.id:
                self._move_to(child, self.stacking.index(surface) + 1)

    def _configured(self, surface):
        self.send(
            "w",
            surface.id,
            surface.x,
            surface.y,
            surface.width,
            surface.height,
        )
