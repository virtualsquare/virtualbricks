COMMONS="--package-name=virtualbricks --package-version=0.3 --msgid-bugs-address=qemulator-list@createweb.de"
JOIN="-j"
LANGUAGES="it nl"
SOURCES="share/*.glade `find virtualbricks/ -type f`"
xgettext -plocale/virtualbricks -ovirtualbricks.pot $JOIN $COMMONS $SOURCES
for l in $LANGUAGES;
do
  xgettext -plocale/virtualbricks -o$l.po $JOIN $COMMONS $SOURCES;
done
