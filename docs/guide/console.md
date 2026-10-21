---
desc: Type commands, run a file of them, or send them from another terminal.
guide: "index#beyond"
seealso:
- remote
sort: 2
---

# The console and scripts

Started from a terminal, Virtualbricks reads the commands of its console there,
beside the windows, unless you give `--no-term`{.cmd}. With `--no-gui`{.cmd} it
runs without the windows, and the console is the way in: a lab on a computer
without a display.

A command is a noun, a verb, then its arguments:

    brick new switch
    brick set vm1 memory=1024 cpus=2
    brick start sw1 vm1
    event start lab
    status

The nouns are `brick`{.cmd}, `event`{.cmd}, `image`{.cmd}, `setting`{.cmd} and
`project`{.cmd}. `help`{.cmd} lists the commands, and `help brick set`{.cmd}
explains one. [Tab]{.key} completes the words, the names and the keys, and the
history is kept between runs.

::: {test="!target:html"}
Every command and option is in [virtualbricks(1)](man:virtualbricks(1)).
:::

::: {test="target:html"}
Every command and option is in
[virtualbricks(1)](https://www.virtualbricks.it/documentation/command-line.html).
:::

## Scripts {#scripts}

A file of commands, one a line, runs with [source *file*]{.cmd} in the console,
or with [virtualbricks --run *file*]{.cmd} at start: a lab set up the same way
every time. The first error stops the file and says which line. An event can
run a command of the console too; see [](events).

## From another terminal {#command}

Started with `--listen`{.cmd}, Virtualbricks takes commands from other
terminals and scripts:

    virtualbricks --listen
    virtualbricks --command brick start sw1
    virtualbricks --connect --run start-lab.vb

The answer goes to the standard output, and the exit status says if the command
was done.
