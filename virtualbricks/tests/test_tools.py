import os
import os.path

from virtualbricks import tools
from virtualbricks.tests import unittest


class MockLock(object):

    def __init__(self):
        self.c = 0

    def __enter__(self):
        self.c += 1

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class TestTools(unittest.TestCase):

    def test_sincronize_with(self):
        lock = MockLock()
        foo_s = tools.synchronize_with(lock)(lambda: None)
        foo_s()
        self.assertEqual(lock.c, 1)
        foo_s()
        self.assertEqual(lock.c, 2)

    def test_tempfile_context(self):
        with tools.Tempfile() as (fd, filename):
            os.close(fd)
            self.assertTrue(os.path.isfile(filename))
        try:
            with tools.Tempfile() as (fd, filename):
                os.close(fd)
                raise RuntimeError
        except RuntimeError:
            self.assertFalse(os.path.isfile(filename))
