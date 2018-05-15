# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

from __future__ import absolute_import
import os
import os.path
import re
import fnmatch

import virtualbricks
from virtualbricks.tests import (unittest, should_test_deployment, skipUnless,
                                 TEST_DATA_PATH)


PATH = os.environ.get("PATH", "")
DEPLOYMENT_PATH = os.environ.get("VIRTUALBRICKS_DEPLOYMENT_PATH", None)
if DEPLOYMENT_PATH is None:
    DEPLOYMENT_PATH = os.path.dirname(virtualbricks.__file__)
GUI_DATA_PATH = os.path.join(DEPLOYMENT_PATH, "gui", "data")
NORMALIZE_RE = re.compile("[^a-zA-Z0-9_]")


GUI_DATA_FILES = set([
    "about.ui",
    "brickselection.ui",
    "captureconfig.ui",
    "capture.png",
    "commitdialog.ui",
    "confirmdialog.ui",
    "createimagedialog.ui",
    "disklibrary.ui",
    "ethernetdialog.ui",
    "eventcommand.ui",
    "eventconfig.ui",
    "event.png",
    "exportproject.ui",
    "help/bandwidth.txt",
    "help/chanbufsize.txt",
    "help/delay.txt",
    "help/loss.txt",
    "importdialog.ui",
    "listprojects.ui",
    "loadimagedialog.ui",
    "logging.ui",
    "networkcards.ui",
    "netemuconfig.ui",
    "netemu.png",
    "newevent.ui",
    "qemuconfig.ui",
    "qemu.png",
    "renamedialog.ui",
    "router.png",
    "saveas.ui",
    "simpleentry.ui",
    "switchconfig.ui",
    "switch.png",
    "switchwrapperconfig.ui",
    "switchwrapper.png",
    "tapconfig.ui",
    "tap.png",
    "tunnelcconfig.ui",
    "tunnelconnect.png",
    "tunnellconfig.ui",
    "tunnellisten.png",
    "usbdev.ui",
    "userwait.ui",
    "virtualbricks.ui",
    "virtualbricks.png",
    "wireconfig.ui",
    "wirefilter.png",
    "wire.png",
])

TEST_DATA_FILES = set([
    "qemu-img",
])

SCRIPTS = [
    "virtualbricks",
]

_data_test_template = """
def test_data_file_{name}(self):
    self.assertTrue(os.access(os.path.join("{data_path}", "{filename}"),
            os.R_OK), "File {filename} not found")
"""

_script_test_template = """
def test_script_{name}(self):
    for path in PATH.split(":"):
        if os.access(os.path.join(path, "{filename}"), os.X_OK):
            break
    else:
        self.fail("Could not find script {filename} in PATH")
"""

_all_data_template = """
def test_{name}_not_tested(self):
    self.fail("{filename} not tested")
"""


@skipUnless(should_test_deployment(), "deployment tests are not enabled")
class TestDeploymentGuiDataFiles(unittest.TestCase):

    # test gui data files
    for datafile in GUI_DATA_FILES:
        test_definition = _data_test_template.format(
            data_path=GUI_DATA_PATH,
            filename=datafile,
            name=NORMALIZE_RE.sub("_", datafile))
        exec (test_definition)


@skipUnless(should_test_deployment(), "deployment tests are not enabled")
class TestDeploymentTestDataFiles(unittest.TestCase):

    # test gui data files
    for datafile in TEST_DATA_FILES:
        test_definition = _data_test_template.format(
            data_path=TEST_DATA_PATH,
            filename=datafile,
            name=NORMALIZE_RE.sub("_", datafile))
        exec (test_definition)


@skipUnless(should_test_deployment(), "deployment tests are not enabled")
class TestDeploymentScripts(unittest.TestCase):

    for script in SCRIPTS:
        test_definition = _script_test_template.format(
            filename=script,
            name=NORMALIZE_RE.sub("_", script))
        exec (test_definition)


def is_py_file(filename):
    return filename.endswith(".py") or filename.endswith(".pyc")


def is_gui_data_file(dirpath, filename):
    cp = os.path.commonprefix((dirpath, GUI_DATA_PATH))
    return (cp == GUI_DATA_PATH and
            os.path.join(dirpath[len(cp)+1:], filename) in GUI_DATA_FILES)


def is_test_data_file(dirpath, filename):
    return dirpath.startswith(TEST_DATA_PATH) and filename in TEST_DATA_FILES


def file_should_be_test_and_it_is_not(dirpath, filename):
    # do not test files under DEPLOYMENT_PATH/tmp
    tmpdir = os.path.join(DEPLOYMENT_PATH, "tmp")
    if os.path.commonprefix((dirpath, tmpdir)) == tmpdir:
        return False
    # do not test swp files
    if fnmatch.fnmatch(filename, ".*.sw?"):
        return False
    return (not (is_gui_data_file(dirpath, filename) or
                 is_test_data_file(dirpath, filename)) and
            not is_py_file(filename))


@skipUnless(should_test_deployment(), "deployment tests are not enabled")
class TestDeploymentDataFilesNotTested(unittest.TestCase):

    for dirpath, dirnames, filenames in os.walk(DEPLOYMENT_PATH):
        for filename in filenames:
            if file_should_be_test_and_it_is_not(dirpath, filename):
                # import pdb; pdb.set_trace()
                test_definition = _all_data_template.format(
                    filename=os.path.join(dirpath, filename),
                    name=NORMALIZE_RE.sub("_", filename))
                exec (test_definition)
