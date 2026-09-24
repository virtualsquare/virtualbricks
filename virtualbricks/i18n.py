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

import gettext
import locale
import site
import sys
from os.path import abspath, dirname, join

DOMAIN = "virtualbricks"
SOURCE_LOCALEDIR = join(dirname(dirname(abspath(__file__))), "locale")


def find_localedir():
    """
    Return the directory that holds the compiled catalogs, or None.

    In a source checkout these are in ``locale/``. Once installed they are
    under ``<prefix>/share/locale``, where prefix is ``sys.prefix`` (or the
    user base for ``pip install --user``). The stdlib default is
    ``sys.base_prefix``, which differs inside a virtualenv.
    """

    localedirs = [SOURCE_LOCALEDIR]
    for prefix in (sys.prefix, site.getuserbase(), sys.base_prefix):
        localedirs.append(join(prefix, "share", "locale"))
    for localedir in localedirs:
        if gettext.find(DOMAIN, localedir):
            return localedir
    return None


def install():
    """Set up translations: the ``_`` builtin and ``gettext.dgettext``."""

    locale.setlocale(locale.LC_ALL, "")
    localedir = find_localedir()
    if localedir is not None:
        gettext.bindtextdomain(DOMAIN, localedir)
    gettext.install(DOMAIN, localedir, names=["gettext"])
