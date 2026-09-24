#!/bin/sh
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team
#
# Update the translations: extract the messages from the sources into the
# template, merge the template into every .po file and compile the catalogs.
#
#   locale/virtualbricks/virtualbricks.pot         template
#   locale/virtualbricks/<lang>.po                 translations
#   locale/<lang>/LC_MESSAGES/virtualbricks.mo     compiled catalogs
#
# The output is stable: running it twice in a row leaves the tree untouched.
# Requires the GNU gettext tools (xgettext, msgmerge, msgfmt).
#
# To add a language run
#   msginit --no-translator -i locale/virtualbricks/virtualbricks.pot \
#       -o locale/virtualbricks/<lang>.po -l <lang>
# then list its catalog in [tool.setuptools.data-files] in pyproject.toml.

set -eu

cd "$(dirname "$0")"

DOMAIN=virtualbricks
POTDIR=locale/$DOMAIN
POT=$POTDIR/$DOMAIN.pot

VERSION=$(sed -n "s/^__version__ = ['\"]\(.*\)['\"]$/\1/p" \
    virtualbricks/__init__.py)

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

find virtualbricks -type f -name '*.py' -not -path 'virtualbricks/tests/*' |
    sort > "$WORKDIR/files"

# Locations without line numbers, otherwise the template would change every
# time a line is added to a source file.
xgettext \
    --files-from="$WORKDIR/files" \
    --output="$DOMAIN.pot" \
    --output-dir="$WORKDIR" \
    --from-code=utf-8 \
    --add-location=file \
    --copyright-holder="Virtualbricks team" \
    --package-name=Virtualbricks \
    --package-version="$VERSION"

# Replace the template only if something other than the creation date changed.
without_date() {
    grep -v '^"POT-Creation-Date:' "$1" || true
}

if [ ! -f "$POT" ] ||
        [ "$(without_date "$POT")" != "$(without_date "$WORKDIR/$DOMAIN.pot")" ]
then
    cp "$WORKDIR/$DOMAIN.pot" "$POT"
fi

for po in "$POTDIR"/??.po; do
    lang=$(basename "$po" .po)
    msgmerge --quiet --update --backup=none "$po" "$POT"
    mkdir -p "locale/$lang/LC_MESSAGES"
    msgfmt --check-format --output-file="locale/$lang/LC_MESSAGES/$DOMAIN.mo" "$po"
done
