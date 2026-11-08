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
Two states, `good`{.sys} and `bad`{.sys}, and a period of 1000 ms. From
`good`{.sys} to `bad`{.sys} 5 %, from `bad`{.sys} to `good`{.sys} 50 %: each
second, a good link turns bad once in twenty times, so after 20 seconds on
average, and a bad one recovers after 2 seconds on average.
:::

## While it runs {#running}

The states, their values, the period and the chances change at once in a
Netemu that runs; the ends when it starts again. Each start begins in the first
state.
