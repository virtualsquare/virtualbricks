from os.path import abspath, dirname, join as joinpath


curdir = dirname(abspath(__file__))


AUTHOR = 'Virtualbricks Team'
SITENAME = 'Virtualbricks'
SITEURL = ''

PATH = 'content'

TIMEZONE = 'Europe/Rome'

DEFAULT_LANG = 'en'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Blogroll
LINKS = (
    ('GitHub', 'https://github.com/virtualsquare/virtualbricks'),
    ('NetEmu', 'https://github.com/virtualsquare/vde-netemu'),
)

# Social widget
SOCIAL = (
    ('Carlo Caini', '/pages/authors.html#carlo-caini'),
    ('Daniele Lacamera', '/pages/authors.html#daniele-lacamera'),
    ('Pietrofrancesco Apollonio', '/pages/authors.html#pietrofrancesco-apollonio'),
    ('Marco Giusti', '/pages/authors.html#marco-giusti'),
)

DEFAULT_PAGINATION = 10

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True

INDEX_SAVE_AS = "news.html"

# Ordering content
PAGE_ORDER_BY = 'page-order'

# Theme
THEME = "notmyidea"
THEME_TEMPLATES_OVERRIDES = [
    joinpath(curdir, "themes/notmyidea"),
]
