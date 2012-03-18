COMMONS="--package-name=virtualbricks --package-version=1.0 --msgid-bugs-address=qemulator-list@createweb.de"
JOIN="-j"
LANGUAGES="it nl es fr de"
SOURCES="share/*.glade `find virtualbricks/ -type f`"
xgettext -plocale/virtualbricks -ovirtualbricks.pot $COMMONS $SOURCES
for l in $LANGUAGES;
do
  xgettext -plocale/virtualbricks -o$l.po $JOIN $COMMONS $SOURCES;
done
