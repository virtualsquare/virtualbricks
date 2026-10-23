---
title: VIRTUALBRICKS-MIGRATE
section: 1
header: Virtualbricks Manual
footer: virtualbricks VERSION
date: DATE
help:
  id: migration
  title: The migration
guide: "index#reference"
sort: 6
---

# NAME

virtualbricks-migrate - convert the files of Virtualbricks 2.1 and older

# SYNOPSIS

**virtualbricks-migrate** [**--in-place**] [**--settings** *file*]
[*input* [*output*]]

**python -m virtualbricks.migrate** [**--settings** *file*]
[**--copy-files**] [**--dry-run**] [**-v**] *input* *output*

**python -m virtualbricks.migrate --in-place** [**--settings** *file*]
[**--dry-run**] [**-v**]

# DESCRIPTION

Virtualbricks 2.1 and older kept their settings in *~/.virtualbricks.conf*
and each project in a *.project* file; this version reads the files of
**virtualbricks-config**(5). The migration converts the old files into the
new ones, as Virtualbricks does by itself the first time it starts after an
upgrade. The old files are only read; what the conversion does to each
setting, brick and event is in the MIGRATION section of
**virtualbricks-config**(5).

**virtualbricks-migrate** opens the window of the migration, filled with
what it's given: the old workspace, *input*, and the folder to write into,
*output*, or with **--in-place** the files of the user. The window shows
what it converted, project by project.

**python -m virtualbricks.migrate** does the same without the window, and
prints what it converted. Given an old workspace and a new or empty
folder, it writes into the folder, laid out like the XDG directories, to
try the migration out on copies:

*output*/config/virtualbricks/settings.toml
:   The settings, from the file of **--settings**.

*output*/state/virtualbricks/state.toml
:   The state, with the project that was open last in the file of
    **--settings**.

*output*/workspace/*project*/project.toml
:   Each project, with its README if it has one.

*output*/migration-report.txt
:   What it converted, as it printed it.

Given **--in-place**, it migrates the files of the user: the settings and
the state go into the XDG directories, and the **project.toml** of each
project next to its *.project* file, in the workspace that the old
settings name.

# OPTIONS

**--gui**
:   Open the window of the migration, as **virtualbricks-migrate** does.
    **--copy-files**, **--dry-run** and **--verbose** aren't available
    there.

**--in-place**
:   Migrate the files of the user, next to the old ones. It takes no
    folders.

**--settings** *file*
:   An old settings file to migrate too. With **--in-place**, it's
    *~/.virtualbricks.conf* if there is one, unless this names another.

**--copy-files**
:   Copy the disks and the other files of each project into *output*
    too; without it, only the converted files and the README are written.
    It's for a migration into a folder.

**--dry-run**
:   Convert and check everything, but write nothing.

**-v**, **--verbose**
:   Print the informational messages too, beside the warnings and the
    errors.

**-h**, **--help**
:   Print the options, then exit.

# EXIT STATUS

**0**
:   Every project was migrated; warnings are fine. **virtualbricks-migrate**
    ends with 0 once its window closes.

**1**
:   A project failed.

**2**
:   The arguments are wrong.

**3**
:   Virtualbricks is running, and the files are to be migrated in place:
    close it first.

# FILES

*~/.virtualbricks.conf*
:   The settings of Virtualbricks 2.1 and older, which **--in-place**
    migrates.

*workspace*/*project*/.project
:   A project of Virtualbricks 2.1 and older.

*\$XDG_STATE_HOME*/virtualbricks/migration-report.txt
:   What the migration in place converted.

# EXAMPLES

Try the migration on copies, then read what it did:

```
python -m virtualbricks.migrate \
    --settings ~/.virtualbricks.conf ~/vb-copy /tmp/vb-test
less /tmp/vb-test/migration-report.txt
```

Check the files of the user, then migrate them:

```
python -m virtualbricks.migrate --in-place --dry-run
python -m virtualbricks.migrate --in-place
```

# SEE ALSO

**virtualbricks**(1), **virtualbricks-config**(5)
