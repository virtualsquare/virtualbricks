#!/bin/sh
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

TMPFILE=$(mktemp)
trap "rm $TMPFILE" EXIT

find virtualbricks/ -type f -name '*.py' -or -name '*.ui' > $TMPFILE
xgettext \
    --files-from=$TMPFILE \
    --output=virtualbricks.pot \
    --output-dir=locale/virtualbricks \
    --from-code=utf-8 \
    --join-existing \
    --copyright-holder="Virtualbricks team" \
    --package-name=Virtualbricks \
    --package-version=$(python setup.py -V)
