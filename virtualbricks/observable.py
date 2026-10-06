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


from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from typing import TypeAlias

# A callback, called with the emitter, then the arguments and the keywords
# it was connected with.
Callback: TypeAlias = Callable[..., object]
Observer: TypeAlias = tuple[Callback, tuple[object, ...], dict[str, object]]


class Observable:
    # TODO: investigate if weakref.WeakValueDictionary can be used to ease the
    # disponse of observables.

    def __init__(self) -> None:
        self._events: dict[str, list[Observer]] = {}
        # how many muted() blocks are open: while there is one, notify()
        # tells no one
        self._muted = 0

    @contextlib.contextmanager
    def muted(self) -> Iterator[None]:
        """A block in which notify() tells no one; the blocks can nest."""

        self._muted += 1
        try:
            yield
        finally:
            self._muted -= 1

    def add_event(self, name: str) -> None:
        if name in self._events:
            raise ValueError("Event %s already present" % name)
        self._events[name] = []

    def add_observer(
        self,
        name: str,
        callback: Callback,
        args: tuple[object, ...],
        kwds: dict[str, object],
    ) -> None:
        assert callable(callback), f"{callable!r} is not callable"
        assert name in self._events, f"Event {name} not present"
        assert (callback, args, kwds) not in self._events[name]
        self._events[name].append((callback, args, kwds))

    def remove_observer(
        self,
        name: str,
        callback: Callback,
        args: tuple[object, ...],
        kwds: dict[str, object],
    ) -> None:
        assert callable(callback), f"{callable!r} is not callable"
        assert name in self._events, f"Event {name} not present"
        self._events[name].remove((callback, args, kwds))

    def notify(self, name: str, emitter: object) -> None:
        assert name in self._events, f"Event {name} not present"
        if not self._muted:
            for callback, args, kwds in self._events[name]:
                callback(emitter, *args, **kwds)

    def __len__(self) -> int:
        return len(self._events)

    def __bool__(self) -> bool:
        return bool(self._events)


class Signal:

    def __init__(self, observable: Observable, name: str) -> None:
        self._observable = observable
        self._name = name
        try:
            observable.add_event(name)
        except ValueError:
            pass

    def connect(
        self, callback: Callback, *args: object, **kwds: object
    ) -> None:
        assert callable(callback), f"{callable!r} is not callable"
        self._observable.add_observer(self._name, callback, args, kwds)

    def disconnect(
        self, callback: Callback, *args: object, **kwds: object
    ) -> None:
        assert callable(callback), f"{callable!r} is not callable"
        self._observable.remove_observer(self._name, callback, args, kwds)

    def notify(self, emitter: object) -> None:
        self._observable.notify(self._name, emitter)
