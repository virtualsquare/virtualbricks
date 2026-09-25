# -*- test-case-name: virtualbricks.tests.test_project -*-
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
Archives of projects, for the export window.

The rest of the projects is in ``virtualbricks.config``. This module goes
when the export runs in the archive process too.
"""

import errno
import os

from twisted.internet import utils, error, defer
from twisted.python import filepath
from twisted.logger import Logger

from virtualbricks.config import projects

logger = Logger()

create_archive = "Create archive in {path}"
extract_archive = "Extract archive in {path}"
include_images = "Including the following images to the project: {images}."


def _complain_on_error(result):
    out, err, code = result
    stderr = err.decode(errors="replace")
    if code != 0:
        logger.warn("{stderr}", stderr=stderr)
        raise error.ProcessTerminated(code)
    logger.info("{stderr}", stderr=stderr)
    return result


class Tgz:

    exe_c = exe_x = "tar"

    def create(
        self,
        pathname,
        directory,
        files,
        images=(),
        run=utils.getProcessOutputAndValue,
    ):
        """Archive the files of the project in directory, and its images."""

        logger.info(create_archive, path=pathname)
        args = ["cfzh", pathname, "-C", directory] + files
        if images:
            logger.info(include_images, images=images)
            prjpath = filepath.FilePath(directory)
            imgs = prjpath.child(".images")
            try:
                imgs.remove()
            except OSError as e:
                if e.errno != errno.ENOENT:
                    return defer.fail(e)
            imgs.makedirs()
            for name, image in images:
                fp = filepath.FilePath(image)
                if fp.exists():
                    link = imgs.child(name)
                    fp.linkTo(link)
                    args.append("/".join(link.segmentsFrom(prjpath)))
        d = run(self.exe_c, args, os.environ)
        d.addCallback(_complain_on_error)
        if images:
            d.addBoth(pass_through(imgs.remove))
        return d

    def extract(
        self, pathname, destination, run=utils.getProcessOutputAndValue
    ):
        logger.info(extract_archive, path=destination)
        args = ["Sxfz", pathname, "-C", destination]
        d = run(self.exe_x, args, os.environ)
        return d.addCallback(_complain_on_error)


class BsdTgz(Tgz):

    exe_c = exe_x = "bsdtar"


def pass_through(function, *args, **kwds):
    def wrapper(arg):
        function(*args, **kwds)
        return arg

    return wrapper


class Archives:
    """Export projects with an archive tool."""

    archive = BsdTgz()

    def __init__(self, workspace=projects):
        self.workspace = workspace

    @property
    def path(self):
        return self.workspace.path

    def export(self, output, directory, files, images=()):
        return self.archive.create(output, directory, files, images)


manager = Archives()
