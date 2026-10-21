# Writing the documentation

The documentation of Virtualbricks is written in pandoc's Markdown, and
`docs/build.py` builds it:

| Source | Built into |
| --- | --- |
| `guide/<page>.md`, the user guide | `built/mallard/<page>.page`, for Yelp |
| `guide/figures/`, its pictures | `built/mallard/figures/`, a copy |
| `man/<page>.<section>.md`, the manual pages | `built/man/<page>.<section>` |

```sh
python docs/build.py            # build what changed
python docs/build.py --check    # only tell what is out of date
```

What is in `built/` is committed, so that installing Virtualbricks needs no
pandoc, and only the script writes it: change the sources, never the
outputs. The `docs` hook of pre-commit runs the script on every commit that
changes a source; then `help/build.py`, the `help` hook, builds the HTML of
the guide from its Mallard pages, with the Yelp tools.

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
| `::: {test="target:html"}` around paragraphs | `if:test`: for one output only |

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

A manual page is the Markdown of a man page as pandoc reads it: its front
matter gives `title`, `section`, `header` and `footer`; VERSION and DATE in
it become the version of Virtualbricks and the date of the page. Bold is
literal text, typed as it is; italics a part to replace. A code block is at
most 64 columns wide, since `man` indents it by 14 in an 80-column terminal:
check with `COLUMNS=80 man -l docs/built/man/virtualbricks.1`. The tests of
`virtualbricks/tests/test_docs.py` read the pages and compare them with the
code.
