import sys
if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest
import __builtin__
__builtin__._ = str  # XXX: Be sure does not break gettext
