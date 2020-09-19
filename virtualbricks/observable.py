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


class Observable:
    # TODO: investigate if weakref.WeakValueDictionary can be used to ease the
    # disponse of observables.

    def __init__(self, *names):
        self.__events = {}
        self._thawed = False
        for name in names:
            self.add_event(name)

    def thaw(self):
        return ThawingSignalContextManager(self)

    def add_event(self, name):
        if name in self.__events:
            raise ValueError("Event %s already present" % name)
        self.__events[name] = []

    def add_observer(self, name, callback, args, kwds):
        assert callable(callback), f'{callable!r} is not callable'
        assert name in self.__events, f'Event {name} not present'
        assert (callback, args, kwds) not in self.__events[name]
        self.__events[name].append((callback, args, kwds))

    def remove_observer(self, name, callback, args, kwds):
        assert callable(callback), f'{callable!r} is not callable'
        assert name in self.__events, f'Event {name} not present'
        self.__events[name].remove((callback, args, kwds))

    def notify(self, name, emitter):
        assert name in self.__events, f'Event {name} not present'
        if not self._thawed:
            for callback, args, kwds in self.__events[name]:
                callback(emitter, *args, **kwds)

    def __len__(self):
        return len(self.__events)

    def __bool__(self):
        return bool(self.__events)


class Signal:

    def __init__(self, observable, name):
        self.__observable = observable
        self.__name = name
        self.__thawed = False
        try:
            observable.add_event(name)
        except ValueError:
            pass

    def connect(self, callback, *args, **kwds):
        assert callable(callback), f'{callable!r} is not callable'
        self.__observable.add_observer(self.__name, callback, args, kwds)

    def disconnect(self, callback, *args, **kwds):
        assert callable(callback), f'{callable!r} is not callable'
        self.__observable.remove_observer(self.__name, callback, args, kwds)

    def notify(self, emitter):
        if not self.__thawed:
            self.__observable.notify(self.__name, emitter)

    def thaw(self):
        return ThawingSignalContextManager(self)


Event = Signal


class ThawingSignalContextManager:

    def __init__(self, signal_or_observer):
        self.context = signal_or_observer
        self.count = 0

    def __enter__(self):
        self.counter += 1
        self.context._thawed = True

    def __exit__(self, exc_type, exc_value, traceback):
        if self.counter > 0:
            self.counter -= 1
            if self.counter == 0:
                self.context._thawed = False
