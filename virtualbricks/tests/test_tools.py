import os
import os.path

from virtualbricks import tools
from virtualbricks.tests import unittest, must_test_threads


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

    @unittest.skipUnless(must_test_threads(), "threads tests non enabled")
    def test_looping_call_function_raise_error(self):
        """Test that if a function raise an error, it is not called again."""

        stop = [False]
        event = [False]

        def func():
            if stop[0]:
                lc.stop()
                event[0] = True
            else:
                stop[0] = True
                raise RuntimeError("BOOM")

        lc = tools.LoopingCall(0.2, self.assertRaises, (RuntimeError, func))
        # lc = tools.LoopingCall(0.001, func)
        lc._LoopingCall__timer.join()
        self.assertFalse(event[0])

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
