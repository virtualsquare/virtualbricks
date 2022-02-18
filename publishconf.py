# This file is only used if you use `make publish` or
# explicitly specify it as your config file.

import os
import sys
sys.path.append(os.curdir)
from pelicanconf import *

# If your site is available via HTTPS, make sure SITEURL begins with https://
# SITEURL = 'https://virtualsquare.github.io/virtualbricks'
SITEURL = 'http://wiki.virtualsquare.org/virtualbricks'
RELATIVE_URLS = False

FEED_ALL_ATOM = 'feeds/all.atom.xml'
CATEGORY_FEED_ATOM = 'feeds/{slug}.atom.xml'

DELETE_OUTPUT_DIRECTORY = True

# Social widget
SOCIAL = (
    ('Carlo Caini', '/virtualbricks/pages/authors.html#carlo-caini'),
    ('Daniele Lacamera', '/virtualbricks/pages/authors.html#daniele-lacamera'),
    ('Pietrofrancesco Apollonio', '/virtualbricks/pages/authors.html#pietrofrancesco-apollonio'),
    ('Marco Giusti', '/virtualbricks/pages/authors.html#marco-giusti'),
)
