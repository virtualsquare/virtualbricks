from os.path import abspath, dirname, join as joinpath


curdir = dirname(abspath(__file__))


AUTHOR = 'Virtualbricks Team'
SITENAME = 'Virtualbricks'
SITEURL = ''

PATH = 'content'

# The documents of the Documentation category bring their stylesheets
STATIC_PATHS = ['images', 'documentation']

TIMEZONE = 'Europe/Rome'

DEFAULT_LANG = 'en'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Social links: all of them in the footer of every page
# (themes/overrides/_includes/footer.html); beside the articles, Elegant
# draws an icon for the networks it knows, as GitHub, and skips the others
SOCIAL = (
    # ('Carlo Caini', '/pages/authors.html#carlo-caini'),
    # ('Daniele Lacamera', '/pages/authors.html#daniele-lacamera'),
    # ('Pietrofrancesco Apollonio', '/pages/authors.html#pietrofrancesco-apollonio'),
    # ('Marco Giusti', '/pages/authors.html#marco-giusti'),
    ('GitHub', 'https://github.com/virtualsquare/virtualbricks',
     'Virtualbricks on GitHub'),
)
SOCIAL_PROFILE_LABEL = 'Virtualbricks on GitHub'

# Elegant has no pagination
DEFAULT_PAGINATION = False

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True

# Ordering content
PAGE_ORDER_BY = 'page-order'
# Categories sort by name: reversed, News comes before Documentation
REVERSE_CATEGORY_ORDER = True

# Theme: Elegant, a git submodule
THEME = joinpath(curdir, "themes/elegant")
THEME_TEMPLATES_OVERRIDES = [
    joinpath(curdir, "themes/overrides"),
]
SITE_DESCRIPTION = (
    'Virtualbricks is a virtualization solution for GNU/Linux: a frontend '
    'for QEMU/KVM virtual machines and VDE virtual networks.'
)
# Elegant has no page for a tag or an author, and no search without a
# plugin. Category pages come from themes/overrides/category.html. No index:
# the home page is content/pages/home.rst, saved as index.html.
DIRECT_TEMPLATES = ['categories', 'tags', 'archives', '404']
TAG_SAVE_AS = ''
AUTHOR_SAVE_AS = ''
