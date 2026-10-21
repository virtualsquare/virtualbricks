============================
Virtualbricks Website branch
============================

This branch is the source code for the `Virtualbricks website`_.

The website is built using Pelican_. Check the documentation for the
general use. Following is the project specific configuration.

.. _Virtualbricks website: https://www.virtualbricks.it
.. _Pelican: https://blog.getpelican.com/

Github pages
============

The website is published using the `Github pages`_. The branch used to
publish the website is gh-pages_. The **website** branch is used to
create the content and to build the html, the **gh-pages** branch is
used to publish the website.

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
(*_includes/footer.html*) and the pages of the Documentation category,
which keep their own design (*doc.html*).

The home page is *content/pages/home.rst*, a hidden page with the slug
*home*, saved as *index.html*: Elegant's own home page, the *index*
template, is not built.

The help and the Documentation
==============================

The user guide, *content/help/C/*, and the pages of the Documentation,
*content/documentation/*, are copies of what a commit of **develop** has:
the HTML of the guide and of its reference, the man pages, that
*docs/build.py* writes into *docs/built/html/*. They are never edited here. The task *sync-docs*, of *tasks.py*, makes them, and
says how to commit them:

.. code::

   $ git fetch virtualsquare
   $ invoke sync-docs virtualsquare/develop
   $ git add content && git commit -m "Help and Documentation of develop 1234abcd"

The guide is copied as it is, with its reference and its style, and Pelican
doesn't read it: *help* is in *STATIC_PATHS*, *ARTICLE_EXCLUDES* and
*PAGE_EXCLUDES*. One thing changes on the way: a link to the site in full,
*https://www.virtualbricks.it/*, links within the site, relative to its
folder, so that a local build doesn't lead to the published site. A page of
the Documentation keeps its head here, the metadata of Pelican; its body is
that of the page of the reference with its name, *NAME.html*, whose links to
the guide lead to *help/C/*; its style, *NAME.css*, is the style of the
guide. A new page starts as a head with an empty body, which the next sync
fills.

*make publish*, and so *make github*, first runs ``invoke sync-docs --check
$(DOCS_REF)``, *develop* unless the command line says otherwise, and stops
while the site differs from it. While 3.0 is in development the site
follows **develop**; once it is out, the latest release:

.. code::

   $ make github DOCS_REF=v3.0.0

*invoke* is in *requirements.txt*.

.. _Elegant: https://github.com/Pelican-Elegant/elegant
