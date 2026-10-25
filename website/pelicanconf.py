from os.path import abspath, dirname
from os.path import join as joinpath

curdir = dirname(abspath(__file__))


AUTHOR = "Virtualbricks Team"
SITENAME = "Virtualbricks"
SITEURL = ""

PATH = "content"

STATIC_PATHS = ["images"]
# The user guide, the HTML that docs/build.py writes into docs/built/html,
# goes into help/C/ as it is, each page with the bar of the site on top
# (plugins/user_guide.py): as the checkout has it, or as the commit DOCS_REF
# has it, a tag or a hash, make publish DOCS_REF=v3.0.0
GUIDE_ROOT = joinpath(curdir, "..")
GUIDE_PATH = "docs/built/html"
DOCS_REF = None
PLUGIN_PATHS = [joinpath(curdir, "plugins")]
PLUGINS = ["user_guide"]

TIMEZONE = "Europe/Rome"

DEFAULT_LANG = "en"

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Social links: all of them in the footer of every page
# (themes/overrides/_includes/footer.html); beside the articles, Elegant
# draws an icon for the networks it knows, as GitHub, and skips the others
SOCIAL = ()
SOCIAL_PROFILE_LABEL = "Virtualbricks on GitHub"

# Beside the text of the home page, as in Elegant's landing page
PROJECTS_TITLE = "Related Projects"
PROJECTS = [
    {
        "name": "Source code",
        "url": "https://github.com/virtualsquare/virtualbricks",
        "description": "Virtualbricks on GitHub",
    },
    {
        "name": "Issues",
        "url": "https://github.com/virtualsquare/virtualbricks/issues",
        "description": "Report a bug or ask a question",
    },
    {
        "name": "NetEmu",
        "url": "https://github.com/virtualsquare/vde-netemu",
        "description": "The channel emulator",
    },
    {
        "name": "VDE",
        "url": "https://wiki.virtualsquare.org/#/?id=virtual-distributed-ethernet-vde",
        "description": "VDE provides an effective communication platform for virtual entities interoperability",
    },
    {
        "name": "Qemu",
        "url": "https://www.qemu.org/",
        "description": "QEMU is a free and open-source machine emulator and virtualizer",
    },
]

# Elegant has no pagination
DEFAULT_PAGINATION = False

# Uncomment following line if you want document-relative URLs when developing
# RELATIVE_URLS = True

# Ordering content
PAGE_ORDER_BY = "page-order"

# Theme: Elegant, a git submodule
THEME = joinpath(curdir, "themes/elegant")
THEME_TEMPLATES_OVERRIDES = [
    joinpath(curdir, "themes/overrides"),
]
SITE_DESCRIPTION = (
    "Virtualbricks is a virtualization solution for GNU/Linux: a frontend "
    "for QEMU/KVM virtual machines and VDE virtual networks."
)
# Elegant has no page for a tag or an author, and no search without a
# plugin. Category pages come from themes/overrides/category.html. No index:
# the home page is content/pages/home.rst, saved as index.html.
DIRECT_TEMPLATES = ["categories", "tags", "archives", "404"]
TAG_SAVE_AS = ""
AUTHOR_SAVE_AS = ""
