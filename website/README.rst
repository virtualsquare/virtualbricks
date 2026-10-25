=========================
The Virtualbricks website
=========================

This folder is the source code of the `Virtualbricks website`_. Until
October 2026 it was a branch of its own, **website**, which came here
with its history (``git log -- website``).

The website is built using Pelican_. Check the documentation for the
general use. Following is the project specific configuration. The
commands run in this folder; *requirements.txt* has what they need, as
does the *website* dependency group of *pyproject.toml*:

.. code::

   $ pip install -r requirements.txt
   $ make html

.. _Virtualbricks website: https://www.virtualbricks.it
.. _Pelican: https://blog.getpelican.com/

Github pages
============

The website is published using the `Github pages`_. The branch used to
publish the website is gh-pages_. This folder is used to create the
content and to build the html, the **gh-pages** branch is used to
publish the website.

The Makefile rule *github* is used to build and publish the website. The
command uses the **virtualsquare** remote. This means you should have a
remote called **virtualsquare** and pointing to
git@github.com:virtualsquare/virtualbricks.git.

Ex.

.. code::

   $ git remote -v
   origin  git@github.com:marcogiusti/virtualbricks.git (fetch)
   origin  git@github.com:marcogiusti/virtualbricks.git (push)
   virtualsquare   git@github.com:virtualsquare/virtualbricks.git (fetch)
   virtualsquare   git@github.com:virtualsquare/virtualbricks.git (push)


.. _Github pages: https://pages.github.com/
.. _gh-pages: https://github.com/virtualsquare/virtualbricks/tree/gh-pages

Theme
=====

The theme is Elegant_, a git submodule in *themes/elegant*, at its
release V5.4.0. After a clone, fetch it with:

.. code::

   $ git submodule update --init

The templates in *themes/overrides* replace or add to those of Elegant:
the menu (*base.html*), the pages with their translations and, on the
home page, the social links and the recent news (*page.html*), the page
of a category (*category.html*), the social links in the footer
(*_includes/footer.html*) and the bar of the site on the pages of the
user guide (*help_bar.html*).

The home page is *content/pages/home.rst*, a hidden page with the slug
*home*, saved as *index.html*: Elegant's own home page, the *index*
template, is not built.

The user guide
==============

The user guide on the site, *help/C/*, is the HTML of the guide and of
its reference, the man pages, that *docs/build.py* writes into
*docs/built/html/*: the same pages that Virtualbricks opens in the
browser without Yelp. The site has no copy of them. Once Pelican has
written the site, the plugin *plugins/user_guide.py* copies them into
it, as they are but for two changes to each page. A link to the site
in full, *https://www.virtualbricks.it/*, as the installed guide needs,
links within the site, relative to its folder, so that a local build
doesn't lead to the published site. And the page gets the bar of the
site, *help_bar.html*, with the menu of the other pages, on top: the
guide has no way back to the site of its own.

The guide is the one of the checkout, and *make publish*, and so *make
github*, stops while *docs/built/html/* has changes not committed. While
3.0 is in development the site is published from **develop**, and its
guide is that of **develop**. Once it is out, the guide should be that
of the latest release: *DOCS_REF* names the commit whose guide the site
has, a tag or a hash, which *git archive* reads.

.. code::

   $ make github DOCS_REF=v3.0.0

.. _Elegant: https://github.com/Pelican-Elegant/elegant
