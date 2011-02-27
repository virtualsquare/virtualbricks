COMMONS="-j --package-name=virtualbricks --package-version=0.3 --msgid-bugs-address=qemulator-list@createweb.de"
LANGUAGES="it_IT nl_NL"
SOURCES="share/*.glade virtualbricks/*"
#xgettext -plocale/virtualbricks -ovirtualbricks_SKELETON.po $COMMONS $SOURCES
for l in $LANGUAGES;
do
  xgettext -plocale/virtualbricks -o$l.po $COMMONS $SOURCES;
done
