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

.. _Elegant: https://github.com/Pelican-Elegant/elegant
