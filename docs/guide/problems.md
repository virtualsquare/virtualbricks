---
desc: The messages, a brick that doesn't start, a refused start, a project that
  can't be read.
guide: "index#beyond"
seealso:
- programs
sort: 5
---

# When something goes wrong

## The messages {#logs}

**File › Logs** has the messages of the run: those of Virtualbricks, of its
bricks, and what their programs print. `level:warning` in its filter keeps the
warnings and the errors, with what the programs wrote on their standard error;
`source:tap1` keeps the messages of the brick `tap1`{.sys}. All about the window
is in [](logs).

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

- Otherwise, filter the **Logs** window with `source:` and the name of the
  brick, as `source:tap1`: its message `Starting:`{.sys} has the command it
  runs, and the program says why it stopped.

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
them to a file; see [](logs#save).
