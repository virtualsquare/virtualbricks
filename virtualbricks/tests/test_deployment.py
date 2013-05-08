import os
import os.path

import virtualbricks
from virtualbricks.tests import unittest


DEPLOYMENT_PATH = os.environ.get("VIRTUALBRICKS_DEPLOYMENT_PATH", None)
if DEPLOYMENT_PATH is None:
    DEPLOYMENT_PATH = os.path.dirname(virtualbricks.__file__)


FILES = [
    "about.ui",
    "capture_gray.png",
    "capture.png",
    "connect_gray.png",
    "connect.png",
    "disconnect_gray.png",
    "disconnect.png",
    "disklibrary.ui",
    "event_gray.png",
    "event.png",
    "joblist.ui",
    "networkcards.ui",
    "qemu_gray.png",
    "qemu.png",
    "remotehosts.ui",
    "router_gray.png",
    "router.png",
    "switch_gray.png",
    "switch.png",
    "switchwrapper_gray.png",
    "switchwrapper.png",
    "tap_gray.png",
    "tap.png",
    "tunnelconnect_gray.png",
    "tunnelconnect.png",
    "tunnellisten_gray.png",
    "tunnellisten.png",
    "usbdev.ui",
    "virtualbricks.glade",
    "virtualbricks.png",
    "wirefilter_gray.png",
    "wirefilter.png",
    "wire_gray.png",
    "wire.png",
]


class TestDeployment(unittest.TestCase):

    def test_static_files(self):
        data_path = os.path.join(DEPLOYMENT_PATH, "gui", "data")
        for filename in FILES:
            self.assertTrue(os.access(os.path.join(data_path, filename),
                                      os.R_OK), "File %s not found" % filename)
