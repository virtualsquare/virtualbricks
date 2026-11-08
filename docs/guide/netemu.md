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
and it moves between them by chance, as a link that degrades and recovers: the
states and the transitions between them are a [Markov
chain](netemu#markov). It runs `vde-netemu`{.cmd}, which Debian and Ubuntu
don't ship; see [](programs).

![The settings of a Netemu: its ends and its
states](figures/netemu-settings.png){alt="The settings of ne1: Left end, sw1, and Right end, sw2; under States of the Markov chain, good, 125000 bytes/s · 10 ms · 0 % lost, selected; bad, 12500 bytes/s · 200 ms · 5 % lost; and down, 125000 bytes/s · 0 ms · 100 % lost; then the buttons + and − and the line The emulator starts in the first state."}

## Ends {#ends}

**Left end**, **Right end**

:   The switches at the two ends, as those of a wire: see [](wires#ends). The
    values go from left to right, from the left end to the right one, and from
    right to left. The socket card of a virtual machine can only be the right
    end.

## States of the Markov chain {#states}

The list has the states of the link, each with its name and its values, as
`125000 bytes/s · 0 ms · 0 % lost`. The link starts in the first state. Select
a state to see its values, and to change them, under **Values of the
selected state**.

The **+** button under the list adds a state after the selected one, named
`state 2`{.sys} or the next free number, with the default values and no chance
of moving to it. The **−** button removes the selected state, unless it is the
only one.

## Values of the selected state {#values}

![The values of the state
good](figures/netemu-values.png){alt="Under Values of the selected state, those of good: Name, good; Bandwidth, 125000; Delay, 10; Buffer, 75000; Loss, 0.00. Each has its number from left to right, →, then its number from right to left, ←, greyed and the same, and the switch Both ways, on."}

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

## Transitions of the Markov chain {#transitions}

![The transitions between good, bad and
down](figures/netemu-transitions.png){alt="Under Transitions of the Markov chain: Period, 1000; then Chances, a grid from a row to a column, with good, bad and down. From good, 5.00 to bad and 1.00 to down, and 94 % stays; from bad, 50.00 to good and 5.00 to down, and 45 % stays; from down, 20.00 to good and 0.00 to bad, and 80 % stays."}

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

## Markov chains {#markov}

A Markov chain is a system that is always in one of a few states, and moves
between them by chance, a step at a time. At each step the chance of each move
depends on the state it is in, and on nothing else: not on the states before,
nor on how long it has been in this one. The chain has no memory. Its chances
are a grid, the transition matrix, with a row for each state it moves from and
a column for each state it moves to; since at each step it moves or stays, a
row adds up to 100 %.

Markov chains model the weather, a queue at a counter, the letters of a text.
For a network link, the classic one is that of Gilbert and Elliott, from the
1960s: a good state, which loses few packets, and a bad one, which loses many,
so that the losses come in bursts, as on a wireless link. In a Netemu each
state has all the values of the link, and a step comes at each **Period**.

## Choosing the chances {#choosing}

Since the chain has no memory, the link leaves a state as a die shows a six:
at each period with the same chance, however long it has waited. A state lasts
on average the period divided by its chance of leaving, but most often a single
period, and now and then many. A state that keeps 80 % leaves with 20 %, after
5 periods on average: one stay in five lasts a single period, and one in ten
more than ten. When it leaves, the link goes to the other states in proportion
to their chances: from `bad`{.sys}, 50 % to `good`{.sys} and 5 % to
`down`{.sys}, so ten times in eleven to `good`{.sys}.

With the three states of the pictures and a period of 1000 ms:

| State | Keeps | Average stay | Share of the time | Loss |
| --- | --- | --- | --- | --- |
| `good`{.sys} | 94 % | 16.7 s | 86 % | 0 % |
| `bad`{.sys} | 45 % | 1.8 s | 8 % | 5 % |
| `down`{.sys} | 80 % | 5 s | 6 % | 100 % |

The share of the time is where the link is in the long run, whatever its first
state, and it comes from the whole grid, not from a row alone. This link loses
6.6 % of its packets on average, almost all of them while down, but never
6.6 % at a time: none for seconds, then all of them for seconds. A Netemu with
a single state and a loss of 6.6 % has the same average, with the losses spread
evenly; the traffic tells them apart (see [](netemu#traffic)).

The chances are for each period: with the same chances, a period half as long
halves every stay. Divide the period and the chances by the same number to
change state at finer times and keep the same stays: 500 ms, with 2.5 % from
`good`{.sys} to `bad`{.sys} and 0.5 % to `down`{.sys}, keeps the 16.7 s of
`good`{.sys}. A state never lasts less than a period.

A state whose column has no chance is never reached, unless it is the first,
which the link starts in and never comes back to once it leaves. A new state,
which **+** adds with no chances, is such a state until you give it some. A
state whose row has no chance keeps 100 %: once there, the link never leaves,
until the Netemu starts again. `down`{.sys} would be one without its 20 % to
`good`{.sys}: the link of the pictures would go down after 75 s on average, and
stay down. So would a group of states that the others lead to, and that leads
back to none of them.

## What the traffic sees {#traffic}

The chain is one for the link, not one for each way: when the state changes,
both ways change at once, and so do the answers, as the acknowledgments of TCP.

A packet takes the values of the state at the moments it crosses the link: when
it enters, whether it is lost and whether the buffer has room for it; when its
turn in the buffer comes, the bandwidth; when it leaves the buffer, the delay.
On its way it keeps what it was given, so a change of state reaches the other
end late, by the time in the buffer and the delay. When the link of the
pictures goes from `bad`{.sys} to `down`{.sys}, the packets already in it still
arrive, for 200 ms and more; those that enter while it is down are lost, even
those that would arrive after it comes back.

Each packet leaves when its own delay ends. When the delay falls, as from the
200 ms of `bad`{.sys} to the 10 ms of `good`{.sys}, the packets that enter after
the change overtake those that entered before it, and arrive out of order. When
it rises, the other end gets nothing for about the difference, 190 ms.

A full buffer takes its size divided by the bandwidth to drain: 75000 bytes,
the default, take 0.6 s at the 125000 bytes/s of `good`{.sys}, but 6 s at the
12500 of `bad`{.sys}. When the link turns bad under a heavy flow, as a
download, the buffer fills: the packets wait in it up to 6 s on top of the
delay, and once it is full those that come are dropped, many more than the 5 %
of the state. A smaller buffer in a slow state keeps the wait short, and drops
more.

The losses come in bursts, which the protocols feel more than as many losses
spread evenly. TCP takes a loss for congestion, and slows down; after an
outage, as the 5 s of `down`{.sys}, it waits longer and longer between its
tries, so that a connection may come back seconds after the link. What runs on
UDP and doesn't resend, as a call or a stream, has gaps instead: it stutters
while the link is bad, and stops while it is down.

Each start draws anew: two runs of the same lab never see the same states at
the same times. A short test can miss a rare state: the link of the pictures
goes down 45 times an hour, once every 80 s on average, and a test of a minute
may never see it.

To follow the chain of a running Netemu, open its console with **Open Control
Monitor**, in the menu of the brick (see [](bricks#process)).
`showcurrent`{.cmd} tells the state the link is in, `markov-debug 1`{.cmd}
prints each change as it comes, and [markov-setnode *n*]{.cmd} moves the link
to the state *n*, counting from 0 in the order of the list; from there it moves
on by chance.

## While it runs {#running}

The states, their values, the period and the chances change at once in a
Netemu that runs; the ends when it starts again. Each start begins in the first
state.
