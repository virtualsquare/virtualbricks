import os
import types
import functools

from twisted.trial import unittest

__builtins__["_"] = str
TEST_THREADS = 0x01
TEST_DEPLOYMENT = 0x02


def should_test_threads():
    return int(os.environ.get("VIRTUALBRICKS_TESTS", 0)) & TEST_THREADS


def should_test_deployment():
    return int(os.environ.get("VIRTUALBRICKS_TESTS", 0)) & TEST_DEPLOYMENT


def _id(obj):
    return obj


def Skip(reason):
    # This decorator is camelcase because otherwise importing it cause all the
    # tests to skip because trial look deep in test method, class, module
    def decorator(test_item):
        if not isinstance(test_item, (type, types.ClassType)):
            @functools.wraps(test_item)
            def skip_wrapper(*args, **kwargs):
                raise unittest.SkipTest(reason)
            test_item = skip_wrapper

        test_item.skip = reason
        return test_item
    return decorator


def skipIf(condition, reason):
    if condition:
        return Skip(reason)
    return _id


def skipUnless(condition, reason):
    if not condition:
        return Skip(reason)
    return _id
