# The Virtualbricks website

This folder is the source of the [Virtualbricks website][site]. Until October
2026 it was a branch of its own, **website**, which came here with its
history (`git log -- website`).

The site is built with [Pelican][pelican]: its documentation tells the
general use, this file what is particular to this site. The commands run in
this folder, but for those that say otherwise.

| Path | What |
| --- | --- |
| `content/pages/` | the pages, with their translations: the home page, `home.rst`, and the authors |
| `content/news/` | the news |
| `content/images/` | the pictures of the pages and of the news |
| `themes/elegant/` | the theme, a git submodule |
| `themes/overrides/` | the templates that replace or add to those of the theme |
| `plugins/user_guide.py` | the plugin that copies the user guide into the site |
| `pelicanconf.py` | the settings of the site, as a local build has it |
| `publishconf.py` | those of the published site, on top of them |
| `BUGS.md` | the bugs of the site found and not fixed yet |

## Build the site

Pelican 4.12 needs Python 3.11 or newer. The `website` dependency group of
`pyproject.toml`, at the top, has what the commands need.
The theme is a submodule: after a clone, fetch it.

```sh
git submodule update --init
pip install --group ../pyproject.toml:website
make html                       # the site, in output/
make devserver PORT=8000        # and serve it at http://localhost:8000
```

`make devserver` builds the site again when a page, a news or the settings
change, not when a template of `themes/overrides/` or the user guide does:
`make html` takes them. `make help` lists the other rules.

## The theme

The theme is [Elegant][elegant], a git submodule in `themes/elegant/`, at its
release V5.4.0.

The templates in `themes/overrides/` replace or add to those of Elegant: the
menu (`base.html`), the pages with their translations and, on the home page,
the social links and the recent news (`page.html`), the page of a category
(`category.html`), the social links in the footer (`_includes/footer.html`)
and the bar of the site on the pages of the user guide (`help_bar.html`).

The home page is `content/pages/home.rst`, a hidden page with the slug
`home`, saved as `index.html`: Elegant's own home page, the `index` template,
is not built.

## The user guide

The user guide on the site, `help/C/`, is the HTML of the guide and of its
reference, the man pages, that `docs/build.py` writes into
`docs/built/html/`: the same pages that Virtualbricks opens in the browser
without Yelp, and those it opens when it finds no guide on the computer
(`virtualbricks/gui/help.py`).

The site has no copy of them. Once Pelican has written the site, the plugin
`plugins/user_guide.py` copies them into it, as they are but for two changes
to each page. A link to the site in full, `https://www.virtualbricks.it/`,
as the installed guide needs, links within the site, relative to its folder,
so that a local build doesn't lead to the published site. And the page gets
the bar of the site, `help_bar.html`, with the menu of the other pages, on
top: the guide has no way back to the site of its own.

The guide is the one of the checkout, unless `DOCS_REF` names a commit, a
tag or a hash, whose guide the site takes: `git archive` reads its
`docs/built/html/`, so the commit must be in the clone.

```sh
make html DOCS_REF=v3.0.0
```

## Update the user guide

The guide is not written here. Its sources are in `docs/`, and the site
takes what `docs/build.py` makes of them: a change to the guide is a commit
to the sources, and its HTML, then a new publication of the site.

1. Change the sources: a page of the guide in `docs/guide/<page>.md`, a man
   page in `docs/man/<page>.<section>.md`. `docs/README.md` tells how a page
   is written.
2. If a window changed, take its pictures again, at the top of the checkout:
   `pytest --pictures -m pictures` writes them into `docs/guide/figures/`
   (see `e2e/README.md`).
3. Build the guide, at the top of the checkout: `python docs/build.py`
   writes `docs/built/`, the HTML, the pages of Yelp and the man pages.
   `python docs/build.py --check` only tells what is out of date.
4. See it in the site: `make html` and `make serve PORT=8000` here, then
   <http://localhost:8000/help/C/>.
5. Commit the sources and `docs/built/` together. The `docs` hook of
   pre-commit runs `docs/build.py` on a commit that changes a source: when
   it rewrites `docs/built/`, the commit stops; add what it wrote and commit
   again.
6. Publish the site, as the next section tells.

## Publish the site

The site is served by [GitHub Pages][pages], at <https://www.virtualbricks.it>,
from the branch [gh-pages][gh-pages] of virtualsquare/virtualbricks. This
folder makes the HTML; **gh-pages** has only the HTML, a commit for each
publication. Nothing publishes the site on its own, neither a push nor a
pipeline: `make github` does, and the whole site goes each time, the guide
with its pages and news.

`make github` pushes to a remote called **virtualsquare**, so the clone needs
one, with the right to push to it, and ghp-import, of the `website` group:

```sh
git remote add virtualsquare git@github.com:virtualsquare/virtualbricks.git
```

Then, in a checkout with the pages and the news to publish:

```sh
git fetch virtualsquare           # gh-pages as it is published, and the tags
make github                       # with the guide of the checkout
make github DOCS_REF=v3.0.0       # with the guide of a release
```

`make github`:

1. runs `make publish`: removes `output/`, stops while `docs/built/html/`
   has changes not committed, unless `DOCS_REF` is given, and builds the site
   with `publishconf.py`, the links in full and the Atom feeds;
2. commits `output/` to the local **gh-pages** with ghp-import, with the
   file `CNAME`, `www.virtualbricks.it`. ghp-import first moves the branch
   to `virtualsquare/gh-pages`, as the last fetch saw it: without the fetch,
   the commit can miss a publication made elsewhere, and the push fails;
3. pushes **gh-pages** to **virtualsquare**.

GitHub serves the new site a few minutes later: look at
<https://www.virtualbricks.it/help/C/> to see the guide.

While 3.0 is in development the site is published from **develop**, and its
guide is that of **develop**: `make github` in a checkout of **develop**,
with the guide committed. Once 3.0 is out, the guide should be that of the
latest release, whatever the checkout has: `make github DOCS_REF=v3.0.0`,
with the tag of the release.

[site]: https://www.virtualbricks.it
[pelican]: https://getpelican.com/
[elegant]: https://github.com/Pelican-Elegant/elegant
[pages]: https://pages.github.com/
[gh-pages]: https://github.com/virtualsquare/virtualbricks/tree/gh-pages
