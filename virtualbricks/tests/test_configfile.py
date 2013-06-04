import os
import shutil
import tempfile

from twisted.python import log

from virtualbricks import configfile
from virtualbricks.tests import unittest, stubs


class TestConfigFile(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.observer = stubs.LoggingObserver()
        log.addObserver(self.observer.emit)

    def tearDown(self):
        shutil.rmtree(self.tmp)
        log.removeObserver(self.observer.emit)

    def test_restore_backup(self):
        filename = os.path.join(self.tmp, "test")
        fbackup = filename + "~"
        configfile.restore_backup(filename, fbackup)
        self.assertEqual(self.observer.msgs, [])
        with open(fbackup, "w"):
            pass
        self.assertTrue(os.path.isfile(fbackup))
        configfile.restore_backup(filename, fbackup)
        self.assertFalse(os.path.isfile(filename + ".back"))
        self.assertEqual(len(self.observer.msgs), 4)
        self.assertFalse(os.path.isfile(fbackup))
        with open(filename, "w"):
            pass
        with open(fbackup, "w"):
            pass
        self.assertTrue(os.path.isfile(filename))
        self.assertTrue(os.path.isfile(fbackup))
        configfile.restore_backup(filename, fbackup)
        self.assertTrue(os.path.isfile(filename + ".back"))
