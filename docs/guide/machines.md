---
desc: The settings of a virtual machine, its disks and network cards, and its console.
guide: "index#kinds"
seealso:
- images
- bricks
sort: 1
---

# Virtual machines

A virtual machine is a brick that QEMU runs. Its settings have a section for
each part of it: **Machine**, the QEMU program, the type of machine, its
processors and its memory; **Disks**; **CD-ROM and boot**; **Network**;
**Display**; **Sound and USB**; **Kernel**, to boot a kernel of your own; and
**Advanced**.

The line at the top says which QEMU will run the machine, and its version. The
lists of machine types, CPU models, sound cards and network cards are what
that QEMU has. When the program isn't there, the line says so, and the lists
have only the choices of the machine. A setting that this QEMU lacks says so
under it, in the colour of warnings, and its section is marked at the left:
the machine starts without it, and the **Logs** window says so.

The settings take effect when the machine starts again.

## Machine {#machine}

![The section Machine](figures/machine-settings.png){alt="The settings of vm1: the line at the top names its QEMU, the sections are at the left, and the section Machine shows Program, Machine type, CPU model, KVM, Virtual CPUs and Memory."}

**Program**

:   The QEMU program, by its architecture, as `x86_64`{.sys} for
    `qemu-system-x86_64`{.cmd}: the list has those in the QEMU folder of the
    project, see [](programs#where). One that isn't there shows as not
    installed. `i386`{.sys} by default.

**Machine type**

:   The type of machine that QEMU emulates, as `q35`{.sys} or `virt`{.sys};
    **The default** for the one of QEMU, which the list names. The programs
    of ARM, and that of RISC-V in QEMU 11, have no default: choose one, as
    `virt`{.sys}, or the machine can't start.

**CPU model**

:   The processor that QEMU emulates; **The default** for the one of QEMU.

**KVM**

:   Run the machine with KVM, the virtualization of the processor of this
    computer, far faster than emulating it. Where KVM can't run, as without
    `/dev/kvm`{.file} or for a processor of another kind, QEMU emulates it
    all the same. Off by default.

**Virtual CPUs**

:   The number of processors of the machine, from 1 to 64; 1 by default.

**Memory**

:   The memory of the machine, in MiB, from 1 to 99999; 64 by default.

**KVM shadow memory**, **Shadow memory**

:   With **KVM**: the memory that KVM keeps for the page tables of the
    machine, in MiB, when the default of QEMU isn't enough. Off by default.

**ACPI**

:   Power management. **Stop** asks the system of the machine to shut down
    through ACPI: without it, the system doesn't hear it, and only
    **Terminate** or **Kill** stop the machine. On by default.

## Disks {#disks}

![The section Disks](figures/machine-disks.png){alt="The section Disks of vm1: the disk hda with the image debian, qcow2, a disk of 1.0 GB, used as a Private copy, and the line under it, vm1's changes will be kept in vm1_hda.cow, made at the next start; debian stays as it is. Add Disk under it, then Changes: Forget the changes and Virtio disks, off."}

**Add Disk** adds a disk on the first free device: `hda`{.sys} to
`hdd`{.sys}, the floppies `fda`{.sys} and `fdb`{.sys}, and `mtdblock`{.sys}.
Each disk chooses its image in a list of the images of the project, which says
what each is and who uses it. The list also has **Add an Existing Image…**,
**New Empty Disk…** and **Manage Images…**, which shows the **Images** tab.

::: {.terms title="How a disk uses its image"}

**Private copy**

:   The default. The machine writes its changes to a file of its own in the
    folder of the project, made at its next start, as `vm1_hda.cow`{.file}, and
    the image stays as it is. Several machines can share one image this way.

**The image itself**

:   The machine writes to the image.
:::

The line under a disk says what it does. The menu of a disk has **Save as a New
Image…**, which keeps the changes of the machine as an image of their own;
**Merge into** the image, which writes them into it, and lists first what else
uses it; **Start Over from** the image, which throws the changes away; **Show
in Files** and **Remove Disk**. Saving and merging run in the background, with
their progress, and can be stopped.

::: {.terms title="Changes"}

**Forget the changes**

:   The machine writes the changes to its disks in temporary files, forgotten
    when it stops: each start begins from the same disks. Off by default.

**Virtio disks**

:   Attach the disks as virtio devices, faster than those of a PC, for a
    system that has their driver, as Linux, which names them
    `vda`{.sys}, `vdb`{.sys} and so on. Off by default.
:::

## CD-ROM and boot {#cdrom}

![The section CD-ROM and boot](figures/machine-cdrom.png){alt="The section CD-ROM and boot of vm1: CD-ROM, Nothing, so Image and Drive are greyed; Boot from, The default."}

**CD-ROM**

:   What the CD-ROM holds: **Nothing**, the default; **An image**, a file as
    an `.iso`{.file}; or **A drive** of this computer.

**Image**

:   With **An image**: the image file. Type it, or choose it with the button
    beside it.

**Drive**

:   With **A drive**: the CD-ROM drive of this computer, as
    `/dev/cdrom`{.file}.

**Boot from**

:   The first place the machine boots from: **The default**, that of QEMU;
    **The first disk**; **The CD-ROM**; **The floppy**; or **The network**.

## Network cards {#network}

![The section Network](figures/machine-network.png){alt="The section Network of vm1: the card eth0, with the button that removes it; Model, rtl8139; MAC address, 52:54:00:12:34:01, with the button that makes another; Plugged into, sw1. Add Card under it."}

**Add Card** adds a card after the others. The cards are in the order the
machine sees them, the first one first, `eth0`{.sys} in the settings. The
button at the end of a card removes it. Each card has:

**Model**

:   The network card that QEMU emulates, of those that this QEMU has;
    `rtl8139`{.sys} by default, or another one where QEMU lacks it.

**MAC address**

:   The address of the card on the network. A new card has a random one; the
    button beside it makes another.

**Plugged into**

:   What the card joins:

    - a switch of the lab, by its name;

    - **The host only, on QEMU's user network**: QEMU joins the machine to
      this computer, and through it to the networks this computer reaches,
      with no switch;

    - **Other bricks plug into it**: the card is a socket, and a wire can plug
      into it when the setting **Plugs into machines** of the project allows
      it, see [](settings#project);

    - **Nothing**: the card goes nowhere, and the machine can't start until you
      plug it in or remove it.

## Display {#display}

![The section Display](figures/machine-display.png){alt="The section Display of vm1: No display, Standard VGA, VNC and SDL window, off, and VNC display, 1, greyed; Keyboard layout, empty, at the bottom."}

**No display**

:   The machine has no screen at all: only its console, and its serial port.
    **VNC** and **SDL window** are then greyed. Off by default.

**Standard VGA**

:   A standard VGA card in place of the one of the machine. Off by default.

**VNC**, **VNC display**

:   Show the screen of the machine over VNC, on the display of that number,
    from 0 to 500; 1 by default. A VNC viewer connects to port 5900 and the
    number, as `vncviewer localhost:1`{.cmd}. Off by default.

**SDL window**

:   Show the screen in a window of SDL. Off by default.

**Keyboard layout**

:   The layout of the keyboard of the machine, two letters, as `it` or `de`;
    empty for that of QEMU.

## Sound and USB {#sound}

![The section Sound and USB](figures/machine-sound.png){alt="The section Sound and USB of vm1: Sound card, None; Audio driver, alsa; USB, off; and under USB devices, greyed, 1d6b:0002, Linux Foundation 2.0 root hub, and 0781:5567, SanDisk Corp. Cruzer Blade, each with its switch."}

**Sound card**

:   **None**, the default; **PC speaker**; or one of the sound cards of this
    QEMU.

**Audio driver**

:   Where the sound goes on this computer, as the **Settings** window says:
    see [](settings#computer).

**USB**

:   Give the machine USB, and the devices below. Off by default.

**USB devices**

:   The USB devices of this computer, each with a switch that gives it to the
    machine. A device that the machine has and this computer hasn't shows as
    not on this host. QEMU runs as you: it needs the right to open the device.

## Kernel {#kernel}

![The section Kernel](figures/machine-kernel.png){alt="The section Kernel of vm1: Boot a kernel, off, so Kernel, Initial ramdisk, Ramdisk and Command line are greyed; under Debugging, GDB, off."}

**Boot a kernel**

:   Boot a kernel of your own, not the one on the disks. Off by default.

**Kernel**

:   With **Boot a kernel**: the file of the kernel.

**Initial ramdisk**, **Ramdisk**

:   With **Boot a kernel**: load an initial ramdisk with the kernel, and its
    file.

**Command line**

:   The command line of the kernel, as `console=ttyS0 root=/dev/vda1`.

**GDB**, **GDB port**

:   Let GDB debug the machine, on that TCP port, from 1 to 65535; 1234 by
    default. In GDB, `target remote localhost:1234`{.cmd}. Off by default.

## Advanced {#advanced}

![The section Advanced](figures/machine-advanced.png){alt="The section Advanced of vm1: Local time, Drift fix and Serial socket, off; Icon, empty, with the button that chooses a file."}

**Local time**

:   Start the clock of the machine at the local time, not UTC, as Windows
    expects. Off by default.

**Drift fix**

:   Correct the drift of the clock of the machine, which a busy computer
    slows down. Off by default.

**Serial socket**

:   Connect the serial port of the machine to a socket,
    `vm1_serial`{.file} for `vm1`{.sys}, in the folder of the sockets of the
    project, see [virtualbricks-config(5)](config-files); a program such as
    `socat`{.cmd} connects to it. Off by default.

**Icon**

:   A picture to show in place of the icon of a virtual machine, in the list
    and in the **Topology** tab.

## The console of a machine {#console}

While the machine runs, **Process › Open Control Monitor**, in its menu, opens
the monitor of QEMU in a terminal, the one of the **Terminal** setting. There
you type the commands of QEMU, as `info network`{.cmd}.

## Stop, suspend, resume {#state}

**Stop** asks the system of the machine to shut down. **Suspend**, under
**Process**, saves the state of the machine in its first disk and stops it;
**Resume** starts it again from there. **Reset** is the reset button of the
machine.
