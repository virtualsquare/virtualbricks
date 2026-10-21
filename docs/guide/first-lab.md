---
desc: A switch and a machine plugged into it, started.
guide: "index#start"
seealso:
- kinds
- machines
sort: 1
---

# Make your first lab

A lab is a project: its bricks, the events that start and stop them, and the
disk images of its machines. The smallest useful one is a switch and a virtual
machine plugged into it. You need a disk image for the machine, as a
`.qcow2`{.file} file with a system installed.

1.  In the **Bricks** tab, click **New Brick** and choose **Switch**. The
    switch is named `sw1`{.sys}, and its settings show: click **OK**.

2.  Click **New Brick** again and choose **Virtual machine**. It is named
    `vm1`{.sys}, and its settings show.

3.  Under **Disks**, click **Add Disk**. In the list of images of the new disk,
    choose **Add an Existing Image…**, then the file of your disk image.

4.  Under **Network**, click **Add Card**, and choose `sw1`{.sys} in **Plugged
    into**.

5.  Click **OK**.

6.  Click the start button of `vm1`{.sys}, in its row. The switch starts first,
    since the machine plugs into it, and both rows say **Running**.

![The first lab,
running](figures/first-lab.png){alt="The Bricks tab with two rows, both Running: sw1, a switch of 32 ports, and vm1, a virtual machine of 64 MiB whose card eth0 is on sw1."}

The disk is a **Private copy** of the image: the machine writes its changes to
a file of its own, in the folder of the project, and the image stays as it is.
See [](images).

Virtualbricks saves the project every three minutes and when it quits. To save
it now, choose **Projects › Save**, or press [Ctrl+S]{.keyseq}.

::: {.note .tip}
The same lab from the console of Virtualbricks:

    image add debian ~/images/debian.qcow2
    brick new switch
    brick new vm
    brick set vm1 hda_image=debian
    brick card add vm1 plug sw1
    brick start vm1

See [](console).
:::
