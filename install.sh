#!/bin/bash

if [ `id -g` -ne 0 ]; then
  echo You have not root privileges.
  echo Try executing \"sudo $0\" or \"su -c './install.sh'\"
  exit -1
fi

# Set version here

python setup.py install --record .filesinstalled

if [ -d .bzr ]; then
  if [[ $1 == "-test" ]]; then 
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
