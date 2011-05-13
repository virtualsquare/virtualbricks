#!/bin/bash

if [ `id -g` -ne 0 ]; then
  echo You have not root privileges.
  echo Try executing \"sudo $0\" or \"su -c './install.sh'\"
  exit -1
fi

echo Starting uninstall process
for i in $(less .filesinstalled); do sudo rm $i 2>/dev/null&&echo File \"$i\" removed; done;
echo Done
