from __future__ import absolute_import
import os
import os.path
import re

import virtualbricks
from virtualbricks.tests import unittest, should_test_deployment, skipUnless


PATH = os.environ.get("PATH", "")
DEPLOYMENT_PATH = os.environ.get("VIRTUALBRICKS_DEPLOYMENT_PATH", None)
if DEPLOYMENT_PATH is None:
    DEPLOYMENT_PATH = os.path.dirname(virtualbricks.__file__)
DATA_PATH = os.path.join(DEPLOYMENT_PATH, "gui", "data")
COMMON_PREFIX = len(DATA_PATH) + 1
NORMALIZE_RE = re.compile("[^a-zA-Z0-9_]")


DATA_FILES = set([
    "about.ui",
    "brickconfigsummary.ui",
    "brickselection.ui",
    "bricks.ui",
    "capture.png",
    "changepwd.ui",
    "confirmdialog.ui",
    "connect.png",
    "disconnect.png",
    "disklibrary.ui",
    "ethernetdialog.ui",
    "eventcommand.ui",
    "eventconfig.ui",
    "event.png",
    "events.ui",
    "joblist.ui",
    "logging.ui",
    "networkcards.ui",
    "newevent.ui",
    "qemu.png",
    "remotehosts.ui",
    "renamedialog.ui",
    "router.png",
    "switchconfig.ui",
    "switch.png",
    "switchwrapper.png",
    "tapconfig.ui",
    "tap.png",
    "tunnelconnect.png",
    "tunnellisten.png",
    "usbdev.ui",
    "virtualbricks.glade",
    "virtualbricks.png",
    "wirefilter.png",
    "wire.png",
])

SCRIPTS = [
    "virtualbricks",
    "vbgui",
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


@skipUnless(should_test_deployment(), "deployment tests not enabled")
class TestDeployment(unittest.TestCase):

    for datafile in DATA_FILES:
        test_definition = _data_test_template.format(
            data_path=DATA_PATH,
            filename=datafile,
            name=NORMALIZE_RE.sub("_", datafile))
        exec test_definition

    for script in SCRIPTS:
        test_definition = _script_test_template.format(
            filename=script,
            name=NORMALIZE_RE.sub("_", script))
        exec test_definition

    # all data files must be tested
    for dirpath, dirnames, filenames in os.walk(DATA_PATH):
        for datafile in filenames:
            datafile = os.path.join(dirpath, datafile)[COMMON_PREFIX:]
            if datafile not in DATA_FILES:
                test_definition = _all_data_template.format(
                    filename=datafile,
                    name=NORMALIZE_RE.sub("_", datafile))
                exec test_definition
