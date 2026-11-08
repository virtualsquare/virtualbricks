---
desc: The bandwidth, delay, buffer and loss of an emulated link, in states that change by chance.
guide: "index#kinds"
seealso:
- kinds
- wires
sort: 5
---

# Netemu

A Netemu is a wire that emulates a network link. The packets between its two
switches wait in a buffer, which drains at the bandwidth of the link; they take
its delay, and some are lost. The link has states, each with its own values,
and it moves between them by chance, as a link that degrades and recovers. It
runs `vde-netemu`{.cmd}, which Debian and Ubuntu don't ship; see
[](programs).

![The settings of a Netemu: its ends and its
states](figures/netemu-settings.png){alt="The settings of ne1: Left end, sw1, and Right end, sw2; under States, good, 125000 bytes/s · 10 ms · 0 % lost, selected; bad, 12500 bytes/s · 200 ms · 5 % lost; and down, 125000 bytes/s · 0 ms · 100 % lost; then the buttons + and − and the line The emulator starts in the first state."}

## Ends {#ends}

**Left end**, **Right end**

:   The switches at the two ends, as those of a wire: see [](wires#ends). The
    values go from left to right, from the left end to the right one, and from
    right to left. The socket card of a virtual machine can only be the right
    end.

## States {#states}

The list has the states of the link, each with its name and its values, as
`125000 bytes/s · 0 ms · 0 % lost`. The link starts in the first state. Select
a state to see its values, and to change them, under **Values**.

The **+** button under the list adds a state after the selected one, named
`state 2`{.sys} or the next free number, with the default values and no chance
of moving to it. The **−** button removes the selected state, unless it is the
only one.

## Values {#values}

![The values of the state
good](figures/netemu-values.png){alt="Under Values, those of good, the state selected: Name, good; Bandwidth, 125000; Delay, 10; Buffer, 75000; Loss, 0.00. Each has its number from left to right, →, then its number from right to left, ←, greyed and the same, and the switch Both ways, on."}

The values of the selected state:

**Name**

:   The name of the state, in the list and in the grid of the transitions. Two
    states can't have the same name.

**Bandwidth**

:   Bytes per second at which the buffer drains, 0 for no limit; 125000 by
    default, a megabit per second.

**Delay**

:   The delay, in milliseconds, that a packet takes one way, on top of its
    time in the buffer; 0 by default.

**Buffer**

:   Bytes that the buffer holds, 0 for no limit; 75000 by default.

**Loss**

:   The percentage of packets lost, from 0 to 100, as 0.1 for one in a
    thousand; 0 by default.

Each value has two numbers, **→** from left to right and **←** from right to
left, and the switch **Both ways**. While it is on, the default, the value is
the same both ways, the one of **→**, and **←** is greyed. Turn it off for a
link that differs each way, as an ADSL line.

## Transitions {#transitions}

![The transitions between good, bad and
down](figures/netemu-transitions.png){alt="Under Transitions: Period, 1000; then Chances, a grid from a row to a column, with good, bad and down. From good, 5.00 to bad and 1.00 to down, and 94 % stays; from bad, 50.00 to good and 5.00 to down, and 45 % stays; from down, 20.00 to good and 0.00 to bad, and 80 % stays."}

**Period**

:   How often, in milliseconds, the link may change state; 100 by default.

**Chances**

:   A grid with a row and a column for each state. The number in the row of a
    state and the column of another is the chance, in %, of moving from the
    first to the second at each period. What a state doesn't give to the
    others it keeps: its own cell, greyed, says how much, as `90 % stays`. The
    chances of a row add up to 100 % at most; more is an error, which keeps
    **OK** greyed.

With a single state, the link keeps its values.

::: note
The three states of the pictures, and a period of 1000 ms: `good`{.sys};
`bad`{.sys}, slow, late and lossy; and `down`{.sys}, which loses every packet.
From `good`{.sys}, 5 % to `bad`{.sys} and 1 % to `down`{.sys}; from
`bad`{.sys}, 50 % to `good`{.sys} and 5 % to `down`{.sys}; from `down`{.sys},
20 % to `good`{.sys}. Each second, a good link turns bad once in twenty times
and goes down once in a hundred; a bad one recovers half of the times; and a
link that is down comes back after 5 seconds on average.
:::

## While it runs {#running}

The states, their values, the period and the chances change at once in a
Netemu that runs; the ends when it starts again. Each start begins in the first
state.
