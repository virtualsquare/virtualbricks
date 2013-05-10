import os
import shutil
import tempfile
import logging

from virtualbricks import configfile
from virtualbricks.tests import unittest, stubs


logging.getLogger("virtualbricks").setLevel(logging.DEBUG)


class TestConfigFile(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.handler = stubs.LoggingHandlerStub()
        logging.getLogger("virtualbricks").addHandler(self.handler)

    def tearDown(self):
        shutil.rmtree(self.tmp)
        logging.getLogger("virtualbricks").removeHandler(self.handler)

    def test_restore_backup(self):
        filename = os.path.join(self.tmp, "test")
        fbackup = filename + "~"
        configfile.restore_backup(filename, fbackup)
        self.assertEqual(self.handler._records, {})
        with open(fbackup, "w"):
            pass
        self.assertTrue(os.path.isfile(fbackup))
        configfile.restore_backup(filename, fbackup)
        self.assertFalse(os.path.isfile(filename + ".back"))
        self.assertTrue(logging.INFO in self.handler._records)
        self.assertEqual(len(self.handler._records[logging.INFO]), 3)
        self.assertFalse(os.path.isfile(fbackup))
        with open(filename, "w"):
            pass
        with open(fbackup, "w"):
            pass
        self.assertTrue(os.path.isfile(filename))
        self.assertTrue(os.path.isfile(fbackup))
        configfile.restore_backup(filename, fbackup)
        self.assertTrue(os.path.isfile(filename + ".back"))
