---
desc: Start a lab in order, after a delay, or run commands.
guide: "index#lab"
seealso:
- "bricks#menu"
sort: 4
---

# Events

An event waits a number of seconds, then runs its actions, all at once: an
action doesn't wait for the one before. An action can:

- **Start a brick** or **Stop a brick**;

- **Start an event** or **Stop an event**;

- run a **Console command** of Virtualbricks, as
  `brick set vm1 memory=512`{.cmd};

- run a **Shell command** of this computer.

## The Events tab {#tab}

**New Event** asks for a **Name** and the seconds to wait, then shows the
settings of the event: **Add Action** adds an action, and the button beside an
action removes it.

![The settings of an
event](figures/event-settings.png){alt="The settings of new_event: wait 5 seconds, then Start a brick, sw1, with the button that removes the action beside it, and Add Action under it."}

The row of an event and its menu have:

**Start**, **Stop**

:   Start the event: it waits, then runs its actions. Stop an event that waits,
    before it runs them. **Waiting**, above the list, shows only the events
    that wait.

**Run Now**

:   Run the actions now, without waiting.

**Configure…**, **Rename…**, **Duplicate**, **Delete…**

:   As for a brick. Before an event goes, the dialog says what goes with it:
    the actions of the other events that start or stop it, and the bricks that
    will no longer run it.

## Starting a lab in order {#order}

Some systems need the network up before they start. Make an event that starts
the switches, and one that waits a few seconds and starts the machines; then
start both:

1.  Make the event `network`{.sys}, which waits 0 seconds, with an action that
    starts each switch.

2.  Make the event `machines`{.sys}, which waits 10 seconds, with an action
    that starts each machine.

3.  Make the event `lab`{.sys}, which waits 0 seconds, with the actions **Start
    an event** `network`{.sys} and **Start an event** `machines`{.sys}.

4.  Start `lab`{.sys}.

## An event when a brick starts or stops {#bricks}

In the menu of a brick, **When It Starts** and **When It Stops** choose an
event to start each time the brick starts or stops, as one that runs a shell
command of this computer once a tap is up.
