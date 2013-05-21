import os
import sys
if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest
import __builtin__
__builtin__._ = str  # XXX: Be sure does not break gettext
import logging

logger = logging.getLogger("virtualbricks")
logger.addHandler(logging.NullHandler())


TEST_THREADS = 0x01
TEST_DEPLOYMENT = 0x02


def test_threads():
    return int(os.environ.get("VIRTUALBRICKS_TESTS", 0)) & TEST_THREADS


def test_deployment():
    return int(os.environ.get("VIRTUALBRICKS_TESTS", 0)) & TEST_DEPLOYMENT
