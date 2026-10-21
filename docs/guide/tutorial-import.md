---
desc: The DTN2hops testbed, from its archive and its disk image, downloaded
  apart.
guide: "index#tutorials"
seealso:
- archives
- images
sort: 1
---

# Import DTN2hops

DTN2hops is a testbed of four virtual machines, `node1`{.sys} to `node4`{.sys},
five switches, a switch wrapper and three channel emulators. It comes in two
files, which you have downloaded into your `Downloads`{.file} folder:

- `DTN2hops_26_Feb_2026.vbp`{.file}, the archive of the testbed: its bricks,
  and the private copy of the disk of each machine, with what was done in it;

- `debian13.tar.gz`{.file}, which holds the disk image that the private copies
  are made on, `debian13.qcow2`{.file}. The archive doesn't hold it.

Before you start, extract `debian13.qcow2`{.file} into `Downloads`{.file},
where it takes 6.8 GB. In a terminal:

    cd ~/Downloads
    tar -xzf debian13.tar.gz

You import the testbed into Virtualbricks. The testbed was made with
Virtualbricks 2.1, and Virtualbricks converts it while it reads the archive.

## Open the archive {#open}

1.  Choose **Projects › Import…**. A window opens, and asks for the archive.

    ![The menu
    Projects](figures/import-menu.png){alt="The main window, with the menu Projects open: Projects…, New Project…, Open Recent, Save, Duplicate…, Rename…, Import… and Export…."}

2.  In it, click **Home**, double-click `Downloads`{.file}, choose
    `DTN2hops_26_Feb_2026.vbp`{.file}, and click **Open**. The Import Project
    window opens, reads the archive, then shows what it holds.

    ![The archive, in
    Downloads](figures/import-archive.png){alt="The window Choose an archive, in the folder Downloads of the home, with DTN2hops_26_Feb_2026.vbp chosen, and the button Open at the bottom right."}

## What the window offers {#options}

![The Import Project window, with the
testbed](figures/import.png){alt="The Import Project window for ~/Downloads/DTN2hops_26_Feb_2026.vbp: the name DTN2hops_26_Feb_2026; 3 × Netemu, 5 × Switch, 1 × Switch wrapper and 4 × Virtual machine; under Images, The archive doesn't have this image; the image debian13, used by node1.hda to node4.hda, with Copy grey and Leave unset chosen; Open the project after the import, on."}

**Name**

:   `DTN2hops_26_Feb_2026`{.sys}, the name of the file. If another project
    already has this name, the window suggests `DTN2hops_26_Feb_2026-2`{.sys}:
    an import never replaces an existing project. You can change it; under the
    input box, the window says if and why a name can't be a project's: it's
    empty, is too long, etc.

The bricks

:   Below the name, how many bricks of each kind the project has, by the names
    of the **Bricks** tab: **Netemu** are the channel emulators.

**Images**

:   **The archive doesn't have this image.**, once the window has looked
    through the archive. Then a row for `debian13`{.sys}, used by the
    `hda`{.sys} disk of each of the four machines, with three choices:

    - **Copy**, from the archive to the shared images of your workspace. It's
      grey: the archive doesn't hold the image, and there is nothing to copy.

    - **Use a file…** of this computer.

    - **Leave unset**: the image stays without its file, until **Find the
      File…**, in the **Images** tab, gives it one.

    **Leave unset** is chosen: the window looked for the image where the
    project had it, `/home/carlo/VB_images/debian13.qcow2`{.file} on the
    computer the testbed was made on, and in your shared images, as
    `debian13.qcow2`{.file} or `debian13`{.file}, and found it in neither. It
    doesn't look in `Downloads`{.file}.

**Open the project after the import**

:   On: once imported, the testbed opens in the main window.

**Import**

:   Grey until the window has read the archive, and whenever something stops
    the import; the window says what.

## Choose the image {#image}

::: {.note .warning}
For this tutorial, choose **Use a file…**, then `debian13.qcow2`{.file}: not
**Copy**, nor **Leave unset**.
:::

1.  In the row of `debian13`{.sys}, click **Use a file…**. In the window that
    opens, click **Home**, double-click `Downloads`{.file}, choose
    `debian13.qcow2`{.file}, the file you extracted from
    `debian13.tar.gz`{.file}, and click **Open**.

    ![The image, in
    Downloads](figures/import-image.png){alt="The window The file of debian13, in the folder Downloads of the home, with DTN2hops_26_Feb_2026.vbp and debian13.qcow2, which is chosen, and the button Open at the bottom right."}

![The image,
chosen](figures/import-ready.png){alt="The Import Project window, with Use a file… chosen for debian13, which uses ~/Downloads/debian13.qcow2, and the button Import at the top right."}

The row now says **Uses \~/Downloads/debian13.qcow2**. The import points the
private copies of the four machines at it, so that they keep what was done in
them. It must be the image the testbed was made on: a private copy holds only
the changes over its image. If you use a different one the machine finds a
damaged disk.

The other two choices don't do for this testbed:

**Copy**

:   Grey: the archive doesn't hold the image.

**Leave unset**

:   The virtual machines can't start until [**Find the File…**](images#menu),
    in the **Images** tab, gives `debian13`{.sys} its file.

::: {.note .tip}
The project uses `debian13.qcow2`{.file} where it is: keep it in
`Downloads`{.file}. To keep it with your other images instead, move it into the
[shared images](images#shared) of your workspace before the import: there, the
window finds it, and chooses **Use a file…** with it by itself.
:::

## Import {#import}

1.  Click **Import**. The window shows the progress, and **Cancel** becomes
    **Stop**: an import stopped removes what it wrote. You can close the
    window, and let the import finish.

    ![The import, under
    way](figures/import-progress.png){alt="The Import Project window during the import: Extracting the archive, with the progress bar a third full, 1.0 MB of 3.2 MB, and under it You can close this window: the Logs window says when the import is done. The button Stop at the top left."}

Once imported, the project opens: the main window shows
`DTN2hops_26_Feb_2026`{.sys}, with its thirteen bricks, all stopped.

![The project,
imported](figures/import-done.png){alt="The main window of the project DTN2hops_26_Feb_2026, on its tab Bricks: 0 of 13 running; sw1 to sw4, switchwrapper, sw5, channel_emulator, sat_channel_emulator, to_host_ch_emulator, then node1, all stopped, with the start button of switchwrapper grey."}

If a brick of the previous project was running before the import, the project
is imported but doesn't open: stop the bricks, then open it from the Projects
window.

The start button of `switchwrapper`{.sys} is grey: a switch wrapper is a switch
that another program runs, at `/var/run/switch/sck`{.file}, and it runs while
that program's switch is there. See [](kinds).
