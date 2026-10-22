---
desc: The messages, a brick that doesn't start, a refused start, a project that
  can't be read.
guide: "index#beyond"
seealso:
- programs
sort: 4
---

# When something goes wrong

## The messages {#logs}

**File › Logs** opens the messages of the run: those of Virtualbricks, of its
bricks, and what their programs print, on a grey band, with `2>`{.sys} before
what a program writes on its standard error. The field at the top filters as
you type ([Ctrl+F]{.keyseq}):

`level:warning`

:   The warnings and the errors, with what the programs wrote on their standard
    error.

`source:tap1,vm1`

:   The messages of those bricks; `source:qemu`, those of every virtual
    machine.

any other word

:   The messages that have it.

The menu of the window has **Save…**, which writes every message to a file,
whatever the filter, and **Report a bug…**, which opens a new email in your
mail program, with the messages attached.

## A brick doesn't start {#start}

- **Not connected**: a plug of the brick goes nowhere. Use **Connect To** in
  its menu, or its settings.

- **Not configured**: a setting it needs is missing; its settings say which.

- **Error**, on the switch wrapper it plugs into: the switch of that folder
  isn't there; the tooltip of the state of the switch wrapper says why. Start
  the switch again, or give the switch wrapper the folder of a switch that
  runs.

- A warning sign in **New Brick**, or a message about a program: the program
  isn't installed; see [](programs).

- Otherwise, filter the **Logs** window with the name of the brick: the program
  says why it stopped.

## A tap or a capture interface doesn't start {#sudo}

They run as root, through `sudo`{.cmd}, which can't ask for your password on a
terminal: Virtualbricks runs it without one. So either:

- a helper asks for the password in a window: install one, as
  `ssh-askpass`{.sys}, and name it in the variable `SUDO_ASKPASS`{.sys} or in a
  line `Path askpass /usr/bin/ssh-askpass` of `/etc/sudo.conf`{.file}; or

- a rule of `sudoers`{.file} lets you run `vde_plug2tap`{.cmd} and
  `vde_pcapplug`{.cmd} without a password, with `NOPASSWD`{.sys}, as a computer
  without a display needs.

Otherwise `sudo`{.cmd} refuses at once, and the **Logs** window shows what it
said.

## Virtualbricks doesn't start {#lock}

Only one Virtualbricks runs on the computer, unless it is started otherwise; a
second one is refused, and the message says which process holds the lock, and
whose it is. To run a lab beside another, start each in its own workspace, with
[virtualbricks --workspace *folder*]{.cmd}; see [](console).

## A project can't be read {#project}

If the project that was open last can't be opened at start, the Projects window
opens and says why. A project written by a newer Virtualbricks is not read, and
not written over. Another problem in the file, as a value out of range, takes
the default and is reported in the **Logs** window, with the setting it is
about.

## Reporting a problem {#report}

Tell us what broke at
[github.com/virtualsquare/virtualbricks/issues](https://github.com/virtualsquare/virtualbricks/issues),
and attach the messages: **Save…**, in the menu of the **Logs** window, writes
them to a file.
