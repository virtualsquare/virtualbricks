#!/bin/sh
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

LANGUAGES="it nl es fr de du"

for lang in $LANGUAGES;
do
  msgmerge \
      --update \
      locale/virtualbricks/${lang}.po \
      --lang=$lang \
      locale/virtualbricks/virtualbricks.pot
done
