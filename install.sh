#!/bin/bash
# Set version here
VERSION_MAJOR=0
VERSION_MINOR=5

VERSION_MICRO=`cat .bzr/branch/last-revision | cut -d ' ' -f1`
VERSION=$VERSION_MAJOR.$VERSION_MINOR.$VERSION_MICRO
cat share/virtualbricks.template.glade | sed -e "s/___VERSION___/$VERSION/g" > share/virtualbricks.glade

python setup.py install --record .filesinstalled
rm -f share/virtualbricks.glade
