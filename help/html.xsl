<?xml version="1.0" encoding="UTF-8"?>
<!--
  What help/build.py adds to the HTML of yelp-xsl, for a browser: yelp-build
  imports it (-x). Yelp shows the pages with its own stylesheets.
-->
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                version="1.0">

<!--
  main is a row flexbox, and its div.page, with min-width: auto, is never
  narrower than its widest picture: the page scrolls sideways, and yelp.js,
  which scales a figure down to its column, never does. yelp.js also gives
  a picture the width of its column rounded, up to a pixel wider: no wider
  than its column, once yelp.js has read its own width, unless zoomed.
-->
<xsl:template name="html.css.custom">
main > div.page { min-width: 0; }
div.figure:not(:has(a.figure-zoomed)) div.media img[data-yelp-original-width] {
  max-width: 100%;
  height: auto;
}
</xsl:template>

</xsl:stylesheet>
