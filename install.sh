#!/bin/bash

if [ `id -g` -ne 0 ]; then
  echo You have not root privileges.
  echo Try executing \"sudo $0\" or \"su -c './install.sh'\"
  exit -1
fi

# Set version here
VERSION_MAJOR=0
VERSION_MINOR=4

VERSION_MICRO=`cat .bzr/branch/last-revision | cut -d ' ' -f1`
VERSION=$VERSION_MAJOR.$VERSION_MINOR.$VERSION_MICRO
cat share/virtualbricks.template.glade | sed -e "s/___VERSION___/$VERSION/g" > share/virtualbricks.glade

python setup.py install --record .filesinstalled
rm -f share/virtualbricks.glade

if [ -d .bzr ]; then
  if [[ $1 != "-notest" ]]; then 
	  echo
	  echo "What follows can be useful for developers."
	  echo "If you are user please ignore it."
	  echo "-------pyflakes---------"
	  pyflakes virtualbricks|grep -v "undefined name '_'"
	  echo "-------pylint---------"
	  pylint --errors --additional-builtins=_ virtualbricks
  	echo "----------------"
  fi
fi

echo "Installation finished."
