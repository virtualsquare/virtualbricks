import os
import os.path

import virtualbricks
from virtualbricks.tests import unittest, test_deployment, skipUnless


DEPLOYMENT_PATH = os.environ.get("VIRTUALBRICKS_DEPLOYMENT_PATH", None)
if DEPLOYMENT_PATH is None:
    DEPLOYMENT_PATH = os.path.dirname(virtualbricks.__file__)


FILES = [
    "about.ui",
    "capture.png",
    "connect.png",
    "disconnect.png",
    "disklibrary.ui",
    "event.png",
    "joblist.ui",
    "logging.ui",
    "networkcards.ui",
    "qemu.png",
    "remotehosts.ui",
    "router.png",
    "switch.png",
    "switchwrapper.png",
    "tap.png",
    "tunnelconnect.png",
    "tunnellisten.png",
    "usbdev.ui",
    "virtualbricks.glade",
    "virtualbricks.png",
    "wirefilter.png",
    "wire.png",
]

SCRIPTS = [
    "virtualbricks",
    "vbgui",
]


@skipUnless(test_deployment(), "deployment tests not enabled")
class TestDeployment(unittest.TestCase):

    def test_static_files(self):
        data_path = os.path.join(DEPLOYMENT_PATH, "gui", "data")
        for filename in FILES:
            self.assertTrue(os.access(os.path.join(data_path, filename),
                                      os.R_OK), "File %s not found" % filename)

    def test_scrips(self):
        for filename in SCRIPTS:
            for path in os.environ.get("PATH", "").split(":"):
                if os.access(os.path.join(path, filename), os.X_OK):
                    break
            else:
                self.fail("Could not find script %s in PATH" % filename)
