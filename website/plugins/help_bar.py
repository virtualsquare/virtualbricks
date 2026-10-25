"""
The bar of the site on top of each page of the user guide.

The help, content/help/C/, is the HTML of a commit of develop, copied as it
is by invoke sync-docs: it has no way back to the site. Once Pelican has
copied it into the output, each page gets the bar of
themes/overrides/help_bar.html, the menu of the site, its style in the head
and its nav first in the body.
"""

import os
import re

from pelican import signals

HELP = "help"
# themes/overrides/help_bar.html
TEMPLATE = "help_bar"

# the context of the site and the templates of the theme, from the generators
site = {}


def keep_site(generators):
    site["context"] = generators[0].context
    site["template"] = generators[0].get_template(TEMPLATE)


def add_bar(pelican):
    folder = os.path.join(pelican.output_path, HELP)
    for path, _, names in os.walk(folder):
        for name in names:
            if name.endswith(".html"):
                add_bar_to(os.path.join(path, name))


def add_bar_to(path):
    with open(path, encoding="utf-8") as file:
        page = file.read()
    if '<nav class="site' in page:
        return
    kind = re.search(r'<div class="page (\w+)">', page)
    bar = site["template"].render(
        site["context"], kind=kind.group(1) if kind else ""
    )
    style, nav = re.fullmatch(
        r"\s*(<style>.*?</style>)\s*(.*?)\s*", bar, re.DOTALL
    ).groups()
    page = page.replace("</head>", style + "\n</head>", 1)
    page = page.replace("<body>\n", "<body>\n" + nav + "\n", 1)
    with open(path, "w", encoding="utf-8") as file:
        file.write(page)


def register():
    signals.all_generators_finalized.connect(keep_site)
    signals.finalized.connect(add_bar)
