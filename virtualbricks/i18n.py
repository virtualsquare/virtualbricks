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

import builtins
import gettext
import locale
import site
import sys
from os.path import abspath, dirname, join

DOMAIN = "virtualbricks"
SOURCE_LOCALEDIR = join(dirname(dirname(abspath(__file__))), "locale")
# The functions that gettext.install() puts in the builtins, besides _.
NAMES = ["gettext", "ngettext"]


# gettext.install() puts gettext and ngettext in the builtins, out of the
# sight of mypy.


def _(message: str) -> str:
    return builtins.gettext(message)  # type: ignore[attr-defined]


def ngettext(singular: str, plural: str, count: int) -> str:
    return builtins.ngettext(  # type: ignore[attr-defined]
        singular, plural, count
    )


def N_(message: str) -> str:
    """
    Mark a message for translation, and return it as it is.

    For a text that stays in English in one place and is translated in
    another: the labels and the help of the settings, English in the
    comments of the files, translated with ``_()`` where a window shows
    them. ``l10n.sh`` extracts the marked messages.
    """

    return message


def find_localedir() -> str | None:
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


def install() -> None:
    """
    Set up translations: the locale, the domain of the C libraries such as
    GTK, and the ``_``, ``gettext`` and ``ngettext`` builtins.
    """

    locale.setlocale(locale.LC_ALL, "")
    localedir = find_localedir()
    if localedir is not None:
        gettext.bindtextdomain(DOMAIN, localedir)
    gettext.install(DOMAIN, localedir, names=NAMES)


# Messages are translated as soon as a module is imported, before the
# application starts: the builtins must be there from the first import.
# install() sets them up again, with the locale of the user.
gettext.install(DOMAIN, find_localedir(), names=NAMES)
