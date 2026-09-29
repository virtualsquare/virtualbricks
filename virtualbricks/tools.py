# -*- test-case-name: virtualbricks.tests.test_tools -*-
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


import os
from functools import update_wrapper

from twisted.internet import utils


def is_running(brick):
    return brick.__isrunning__()


def sync():
    """
    Run the sync command wrapped in a deferred. Raise RuntimeError if the
    command fails.

    :rtype: twisted.internet.defer.Deferred[None]
    """

    def complain_on_error(command_info):
        stdout, stderr, exit_status = command_info
        if exit_status != 0:
            raise RuntimeError(f"sync failed\n{stderr}")

    deferred = utils.getProcessOutputAndValue("sync", env=os.environ)
    deferred.addCallback(complain_on_error)
    return deferred


def discard_first_arg(func, *args, **kwds):
    """
    Call func with the given parameters but discard the first one. Useful used
    together with Deferred `addCallback()`. Ex.

        deferred = getProcessValue(['echo', 'hello world'])
        deferred.addCallback(discard_first_arg(print 'hello world2'))

    :param Callable func: the function to wrap.
    :param Tuple args: optional parameters to pass to func.
    :param Dict[str, Any] kwds: optional keyword parameters to pass to func.
    :rtype: Callable
    """

    def wrapper(first_arg, *fargs, **fkwds):
        newkwds = {**kwds, **fkwds}
        return func(*args, *fargs, **newkwds)

    update_wrapper(wrapper, func)
    return wrapper
