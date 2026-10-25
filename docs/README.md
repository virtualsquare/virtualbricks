# Writing the documentation

The documentation of Virtualbricks is written in pandoc's Markdown, and
`docs/build.py` builds it:

| Source | Built into |
| --- | --- |
| `guide/<page>.md`, the user guide | `built/mallard/<page>.page`, for Yelp, and `built/html/<page>.html` |
| `guide/figures/`, its pictures | a copy in `built/mallard/figures/` and in `built/html/figures/` |
| `man/<page>.<section>.md`, the manual pages | `built/man/<page>.<section>`, and a page of the guide, `<id>.page` and `<id>.html`, in its Reference |
| `templates/page.html`, `templates/style.css` | the page and the style of the HTML |

```sh
python docs/build.py            # build what changed
python docs/build.py --check    # only tell what is out of date
```

What is in `built/` is committed, so that installing Virtualbricks needs no
pandoc, and only the script writes it: change the sources, never the
outputs. The `docs` hook of pre-commit runs the script on every commit that
changes a source.

The HTML is for a computer without Yelp, where Virtualbricks opens it in the
browser, and for the website, `website/`, which copies it as it builds. It has
what Yelp adds to a page: the way back to the sections of the index that list
it, See also, with the pages it names and those that name it, and the lists of
the index, each page with the line of its `desc`. Its links stay in the tree,
so that it works without the network: a link to a page names its file,
`command-line.html`.

The design pages of `redesign/` are written in HTML, by hand, and stay out of
the build.

## A page of the guide

```markdown
---
guide: "index#lab"
seealso:
- images
- bricks
sort: 2
desc: The disks, network cards and consoles of a virtual machine.
---

# Virtual machines

A virtual machine is a brick that QEMU runs. …

## Disks {#disks}

**Add Disk** adds a disk on the first free device. …
```

The name of the file, without `.md`, is the id of the page: what links and
`help:virtualbricks/machines` name, and what F1 opens.

The front matter:

| Key | What |
| --- | --- |
| `guide` | the section of the index that lists the page, as `index#lab` |
| `seealso` | the pages that See Also lists; Yelp lists this page in theirs too |
| `sort` | the place of the page in its section of the index |
| `desc` | the line under its title in the index |
| `type` | `guide` for the index; a page is a topic otherwise |
| `title-text` | the title as plain text, where the title has marks |

The page starts with its title, `# Title`. Its sections are `## Title {#id}`,
always with their id, since links name it: a section never takes an id from
its title. There is no third level. A section of the index can have
`{#start style="2column"}`.

## The marks

| Markdown | Mallard | What |
| --- | --- | --- |
| `**Add Disk**` | `<gui>` | a label of a window, a button, a menu |
| `**Projects › Import…**` | `<guiseq>` | a path in the menus, with ` › ` |
| `[F1]{.key}` | `<key>` | a key |
| `[Ctrl+Q]{.keyseq}` | `<keyseq>` | keys together; `[Ctrl++]{.keyseq}` is Ctrl and + |
| `` `info network`{.cmd} `` | `<cmd>` | a command |
| `[virtualbricks --run *file*]{.cmd}` | `<cmd>` with `<var>` | a command with a part to replace |
| `*file*` | `<var>` | a part to replace |
| `` `node1`{.sys} `` | `<sys>` | a name of the system: a host, a brick |
| `` `Downloads`{.file} `` | `<file>` | a file or a folder |
| `` `vm1_hda` `` | `<code>` | any other literal text |
| `[Virtualbricks]{.app}` | `<app>` | the name of a program |
| `[the images](images#shared)` | `<link xref>` | a page, or a section of it |
| `[virtualbricks(1)](command-line)` | `<link xref>` | a page of the Reference, by its id |
| `[](images)` | `<link xref>` | a page, by its title |
| `[issues](https://…)` | `<link href>` | anything else, with its scheme |

Bold is always a label in the guide: there is no other strong emphasis.

## The blocks

| Markdown | Mallard |
| --- | --- |
| a list, `- …` | `<list>` |
| a numbered list, `1. …` | `<steps>`, a procedure |
| a list of terms, `term` then `:   …` | `<terms>` |
| `::: {.terms title="…"}` around a list of terms | the title of the list |
| `::: note`, `::: {.note .tip}`, `::: {.note .warning}` | `<note>` |
| a code block | `<screen>` |
| a table | `<table>` |

A picture is a paragraph of its own:

```markdown
![The settings of a virtual machine](figures/machine-settings.png){alt="The settings of vm1: …"}
```

The text in brackets is the title of the figure, `alt` what the picture
shows, for those who don't see it; both are required. The pictures are in
`guide/figures/`, taken by the end-to-end tests:
`pytest --pictures -m pictures` (see
[e2e/README.md](../e2e/README.md#the-pictures-of-the-user-guide)).

Anything else, a heading of the third level, a span or a code of another
class, a block quote, stops the build with an error: the script never drops
a part of a page.

## The manual pages

A manual page is the Markdown of a man page as pandoc reads it, and a page of
the guide too, in its Reference section: Yelp shows it as it shows the guide,
and opens no other program for it.

```markdown
---
title: VIRTUALBRICKS-CONFIG
section: 5
header: Virtualbricks Manual
footer: virtualbricks VERSION
date: DATE
help:
  id: config-files
  title: Configuration files
guide: "index#reference"
sort: 2
---

# NAME

virtualbricks-config - settings, state and project files of Virtualbricks

# SYNOPSIS

*\$XDG_CONFIG_HOME*/virtualbricks/settings.toml\
*\$XDG_STATE_HOME*/virtualbricks/state.toml
```

`title`, `section`, `header`, `footer` and `date` are those of the man page;
VERSION and DATE become the version of Virtualbricks and the date of the
page. `help` names the page of the guide: its id, which is also the name of
its web page, and its title; `guide` and `sort` place it in the index, as for
a page of the guide.

In the guide:

- NAME, `name - what it is`, is the line under the title in the index:
  virtualbricks-config(5): settings, state and project files of Virtualbricks.
- SYNOPSIS is a synopsis, a line for each line of the man page; a line
  ends with `\`, which is a line break nowhere else.
- A heading in capitals is in sentence case: `# COMMON RULES` is *Common
  rules*; AMP, JSON, README, TOML and Virtualbricks keep their capitals
  (`CAPITALS` in `build.py`). Any other title is given:
  `# CONTENTS.TOML {title="contents.toml"}`. The sections nest, up to `###`.
- Bold is literal text, typed as it is, `<code>`; italics a part to replace,
  `<var>`.
- `**virtualbricks-config**(5)`, a man page of the Reference, is a link to its
  page; the man pages of other programs, as `**tar**(1)`, stay text.
- A numbered list is a list, not a procedure.

In the HTML:

- A list whose terms are all keys, ``**name** = *type* range, default
  `value` ``, is a table: Key, Type, Default, if one has it, and Meaning.
- A power, `2^53-1`, is raised, 2<sup>53</sup>−1, and a range of a key takes
  a dash, 0–2<sup>53</sup>−1.
- A diagram is a drawing, in its place:

````markdown
::: {.diagram svg="figures/control-token.svg"}
```
  client                               Virtualbricks
    |                                        |
```

The messages of the proof come before any other on a socket that asks for
the token.
:::
````

  The man page shows the ASCII, then the paragraph, the caption of the
  drawing in the HTML: it says what both show. Yelp shows the paragraph
  above the ASCII, as a listing, not a figure: Yelp centers each line of
  what a figure holds, which would break the columns. The drawing is an SVG
  file of `man/figures/`, put inline in the page, so that it takes the
  colours of the page, light or dark, from the classes of `.dg` in
  `templates/style.css`. With `.listing` too, as
  `{.diagram .listing svg="…"}`, the block is a listing that the drawing
  doesn't replace: the HTML shows the drawing, then the listing.

A code block is at most 64 columns wide, since `man` indents it by 14 in an
80-column terminal: check with `COLUMNS=80 man -l
docs/built/man/virtualbricks.1`. The tests of `virtualbricks/tests/test_docs.py`
read the pages and compare them with the code.
