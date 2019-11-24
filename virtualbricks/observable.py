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

    thawed = False

    def __init__(self, *names):
        self.__events = {}
        for name in names:
            self.add_event(name)

    def set_thaw(self, value):
        self.thawed = value

    def add_event(self, name):
        if name in self.__events:
            raise ValueError("Event %s already present" % name)
        self.__events[name] = []

    def add_observer(self, name, callback, args, kwds):
        if name not in self.__events:
            raise ValueError("Event %s not present" % name)
        if not callable(callback):
            raise TypeError("%r is not callable" % (callback, ))
        self.__events[name].append((callback, args, kwds))

    def remove_observer(self, name, callback, args, kwds):
        if name not in self.__events:
            raise ValueError("Event %s not present" % name)
        if not callable(callback):
            raise TypeError("%r is not callable" % (callback, ))
        self.__events[name].remove((callback, args, kwds))

    def notify(self, name, emitter):
        if name not in self.__events:
            raise ValueError("Event %s not present" % name)
        if not self.thawed:
            for callback, args, kwds in self.__events[name]:
                callback(emitter, *args, **kwds)

    def __len__(self):
        return len(self.__events)

    def __bool__(self):
        return bool(self.__events)


class Event:

    def __init__(self, observable, name):
        self.__observable = observable
        self.__name = name

    def connect(self, callback, *args, **kwds):
        if not callable(callback):
            raise TypeError("%r is not callable" % (callback, ))
        self.__observable.add_observer(self.__name, callback, args, kwds)

    def disconnect(self, callback, *args, **kwds):
        if not callable(callback):
            raise TypeError("%r is not callable" % (callback, ))
        self.__observable.remove_observer(self.__name, callback, (), {})


class thaw:

    def __init__(self, observable):
        self.observable = observable

    def __enter__(self):
        self.observable.set_thaw(True)

    def __exit__(self, exc_type, exc_value, traceback):
        self.observable.set_thaw(False)
