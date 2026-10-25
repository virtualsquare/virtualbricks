"""
The user guide on the site, in help/C/, with the bar of the site on top of
each page.

The guide is the HTML that docs/build.py writes into docs/built/html: as
the checkout has it or, with the setting DOCS_REF, as a commit has it. Once
Pelican has written the site, each file of the guide is copied into it as
it is, but for two changes to its pages. A link to the site in full,
https://www.virtualbricks.it/, as the installed guide needs, leads within
the site, relative to the folder of the page, so that a local build stays
local. And each page gets the bar of themes/overrides/help_bar.html, the
menu of the site: its style in the head and its nav first in the body.
"""

import io
import os
import re
import subprocess
import tarfile

from pelican import signals

# where the guide goes in the site
HELP = os.path.join("help", "C")
# themes/overrides/help_bar.html
TEMPLATE = "help_bar"
# the address of the site, which the guide links in full
SITE = "https://www.virtualbricks.it/"

# the context of the site and the templates of the theme, from the generators
site = {}


def keep_site(generators):
    site["context"] = generators[0].context
    site["template"] = generators[0].get_template(TEMPLATE)


def guide(settings):
    """The files of the guide, their bytes by their path in it."""
    root, path = settings["GUIDE_ROOT"], settings["GUIDE_PATH"]
    if settings.get("DOCS_REF"):
        return guide_of(root, path, settings["DOCS_REF"])
    folder = os.path.join(root, path)
    if not os.path.isdir(folder):
        raise RuntimeError(f"no user guide in {folder}")
    files = {}
    for parent, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(parent, name)
            with open(path, "rb") as file:
                files[os.path.relpath(path, folder)] = file.read()
    return files


def guide_of(root, path, ref):
    """The files of the guide as the commit ref has them."""
    git = subprocess.run(
        ["git", "-C", root, "archive", "--format=tar", ref, path],
        capture_output=True,
    )
    if git.returncode:
        raise RuntimeError(
            f"DOCS_REF {ref}: {git.stderr.decode().strip()}: git fetch, or "
            "name another"
        )
    files = {}
    with tarfile.open(fileobj=io.BytesIO(git.stdout)) as archive:
        for member in archive.getmembers():
            if member.isfile():
                name = os.path.relpath(member.name, path)
                files[name] = archive.extractfile(member).read()
    return files


def page(text, path, output):
    """The page of the guide at path in the site, from its text."""
    up = os.path.relpath(output, os.path.dirname(path))
    text = text.replace('href="' + SITE, 'href="' + up + "/")
    kind = re.search(r'<div class="page (\w+)">', text)
    bar = site["template"].render(
        site["context"], kind=kind.group(1) if kind else ""
    )
    style, nav = re.fullmatch(
        r"\s*(<style>.*?</style>)\s*(.*?)\s*", bar, re.DOTALL
    ).groups()
    text = text.replace("</head>", style + "\n</head>", 1)
    return text.replace("<body>\n", "<body>\n" + nav + "\n", 1)


def copy_guide(pelican):
    output = pelican.output_path
    for name, data in sorted(guide(pelican.settings).items()):
        path = os.path.join(output, HELP, name)
        if name.endswith(".html"):
            data = page(data.decode("utf-8"), path, output).encode("utf-8")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as file:
            file.write(data)


def register():
    signals.all_generators_finalized.connect(keep_site)
    signals.finalized.connect(copy_guide)
