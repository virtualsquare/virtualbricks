---
desc: A lab on another computer, with its windows on your desktop.
guide: "index#beyond"
seealso:
- console
sort: 3
---

# Another computer

The bricks can run on one computer, the lab machine, and the windows on
another, your desktop. The lab machine runs Virtualbricks with
`--listen`{.cmd}, with its own windows or without, and your desktop opens its
windows with `--connect`{.cmd}. Both run the same version of Virtualbricks.

    # on the lab machine
    virtualbricks --no-gui --no-term --listen \
        'ssl:8765:interface=0.0.0.0:privateKey=~/vb/lab.key'
    # on your desktop
    virtualbricks --connect 'ssl:lab.example:8765:caCertsDir=~/vb/lab'

A connection over the network proves that it knows the token of the lab
machine, the file `~/.config/virtualbricks/token`{.file}, so copy it to your
desktop; or the lab machine asks for the certificate of your desktop instead.
`virtualbricks --connect`{.cmd} alone opens the windows of a Virtualbricks of
yours on this computer, started with `--listen`{.cmd}.

::: {test="!target:html"}
How to listen and connect, the token and the certificates are in
[virtualbricks(1)](man:virtualbricks(1)), and the protocols in
[virtualbricks-control(7)](man:virtualbricks-control(7)).
:::

::: {test="target:html"}
How to listen and connect, the token and the certificates are in
[virtualbricks(1)](https://www.virtualbricks.it/documentation/command-line.html),
and the protocols in
[virtualbricks-control(7)](https://www.virtualbricks.it/documentation/control-protocols.html).
:::

## What the windows do {#windows}

- They follow the project open there, whoever changes it, and what you do goes
  there: a start, a new brick, the **OK** of the settings of a brick.

- What they show is the lab machine's: its QEMU programs, its USB devices, its
  files and its projects. A path is a path there, typed with the completion of
  its folders.

- The consoles of the bricks open in a terminal of your desktop.

- **Settings** has a page for your desktop, one for the lab machine, and one
  for the project.

- Import, export, the long work on images and **Show in Files** wait for a
  later version, greyed.

When the connection is lost, a bar says why, and **Reconnect** connects again.
**Quit** closes the windows: the Virtualbricks on the lab machine goes on.
