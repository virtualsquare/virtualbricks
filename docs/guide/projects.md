---
desc: Open, make, rename, copy and remove the projects of a workspace.
guide: "index#projects"
seealso:
- archives
sort: 1
---

# Projects

A project is a lab: its bricks, its events, its disk images and its README.
Each is a folder of the workspace, with the file `project.toml`{.file}, the
`README.md`{.file} and the private copies of the disks of its machines.
Virtualbricks opens the project that was open last.

## The Projects window {#window}

Choose **Projects › Projects…**, or press [Ctrl+O]{.keyseq}. The list has the
projects of the workspace, the last used first, each with the first line of its
README, its bricks and when it was used last. A project whose images are
missing, or whose file can't be read, says so. Typing filters the list by name
and description. Beside the list, the selected project shows its README, its
bricks, events and images, and the space that it takes.

![The Projects
window](figures/projects.png){alt="The Projects window: new_project and new_project-2 in the list, each with its bricks and when it was used last; beside the list, the details of new_project-2, the project that is open."}

**Open**

:   Save the open project, and open the selected one.

**New…**

:   A new, empty project, with a copy of the settings of the open one; also
    **Projects › New Project…**, [Ctrl+N]{.keyseq}.

**Duplicate…**

:   A copy of the project, with the private copies of its disks but not its
    images, which the copy shares.

**Rename…**

:   A new name; the dialog says at once if a name can't be used.

**Show in Files**

:   The folder of the project, in the file manager.

**Remove…**

:   The folder of the project goes to the trash, where you can restore it, or,
    where the workspace has no trash, is deleted for good. The dialog says how
    much it takes. The images it uses stay where they are. The open project
    can't be removed: open another one first.

**Import…**, **Export…**

:   A project in one file; see [](archives).

## Saving {#save}

Virtualbricks saves the open project every three minutes, when you open another
one and when it quits. **Projects › Save**, [Ctrl+S]{.keyseq}, saves it now.

::: {.note .warning}
Don't edit `project.toml`{.file} while Virtualbricks runs with the project
open: the next save writes over your changes.
:::

## Workspaces {#workspace}

A workspace is a folder of projects, `~/.virtualbricks`{.file} unless the
setting `workspace`{.sys} names another; the **Settings** window shows which.
It keeps the images that its projects share, in `shared_images`{.file}. Started
with [virtualbricks --workspace *folder*]{.cmd}, Virtualbricks uses another
folder for that run, made if it isn't there, and a Virtualbricks can run in
each workspace side by side.

## At start {#start-up}

If the project that was open last can't be opened, the Projects window opens
and says why. A project written by a newer Virtualbricks is not read, and never
written over.
