---
desc: Notes on the lab, in Markdown, with pictures.
guide: "index#lab"
seealso:
- "topology#export"
sort: 6
---

# The README of a project

Each project has a README, the file `README.md`{.file} of its folder: what the
lab is for, its addresses, how to use it. The **Readme** tab shows it rendered.
The Projects window shows it too, and the Import window its first paragraph.

![The Readme
tab](figures/readme.png){alt="The Readme tab: the README rendered, with a heading, a paragraph, a list and a link; Edit and Preview over the top right corner."}

Two buttons float over the top right corner of the tab: **Edit** opens the
text, and **Preview** goes back to the rendered README. While you write,
**Syntax** shows what the text can hold. The README is saved 30 seconds after
your last change, and when you leave the tab.

::: {.terms title="The syntax"}

`# Title`

:   A heading; `##` for a smaller one.

`*emphasis*`, `**strong**`, `~~struck~~`

:   Emphasis, strong and struck text.

`` `code` ``

:   Code; ```` ``` ```` above and below a block of it.

`- item`

:   A list; `1.` for a numbered one.

`> quote`

:   A quote.

`[text](https://example.org)`

:   A link, which opens in your browser; a bare URL is one too.

`![The lab](topology.png)`

:   A picture: a file of the folder of the project, of at most 10 MB.

`---`

:   A line across.
:::

Anything else shows as you typed it. A new line in a paragraph stays a new
line, so a README written as plain text keeps its lines.
