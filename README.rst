============================
Virtualbricks Website branch
============================

This branch is the source code for the `Virtualbricks website`_.

The website is built using Pelican_. Check the documentation for the
general use. Following is the project specific configuration.

.. _Virtualbricks website: https://virtualsquare.github.io/virtualbricks
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
