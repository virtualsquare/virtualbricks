---
desc: See how the bricks connect, and export the picture.
guide: "index#lab"
seealso:
- readme
sort: 5
---

# The picture of the lab

The **Topology** tab draws the bricks of the project and the links between
them. A stopped brick is grey. The brick under the pointer lights up, and its
tooltip says its name, its kind and its state. The right button opens the menu
of the brick, as in the **Bricks** tab, and a double click its settings.

![The Topology
tab](figures/topology.png){alt="The Topology tab: sw1 and vm1, joined by a line, with the buttons of the zoom over the top right corner."}

## Zooming {#zoom}

A bar over the top right corner has **Zoom Out**, the zoom level, **Zoom In**,
**Fit All** and a menu. A click on the level goes back to 100%. The tab opens
with the whole lab in view, and keeps it in view as the lab changes, until you
zoom.

- [Ctrl++]{.keyseq}, [Ctrl+-]{.keyseq}: zoom in and out; [Ctrl+0]{.keyseq}:
  100%; [F]{.key}: fit all.

- [Ctrl]{.key} and the wheel of the mouse, or a pinch on a touchpad, zoom
  around the pointer.

- Dragging the background moves the picture.

## Connecting two bricks {#connect}

Drag a brick onto another, as in the **Bricks** tab: a line follows the
pointer. Over a brick that it can plug into, or that can plug into it, the
line ends on that brick, which lights up, and the words under it say what
letting go does, as **Connect tap1 to sw2**. Let go there, and the two connect,
as with **Connect To** in the menu of the brick; let go over another brick, or
press [Esc]{.key}, and nothing changes. Near an edge of the tab, the picture
scrolls, to reach a brick out of view.

## Moving bricks {#move}

Drag a brick and let go over free room: the brick stays there. On the way, a
faded copy of it at the end of the line shows where it goes. Near the column
or the row of another brick, the copy lines up with it, and a thin line shows
it.

The first move keeps every other brick where it shows: the lab is laid out by
hand from then on, and the project keeps the place of each brick, so the
picture stays as you arranged it, after a restart and in an exported archive.
A new brick waits in a row under the others until you move it.

## Layout and export {#export}

The menu of the bar has the **Layout**: **Left to Right** or **Top to Bottom**,
where Graphviz places the bricks again after each change, or **By Hand**, where
each brick stays at its place. **By Hand** gives every brick the place it has
in the picture; **Left to Right** and **Top to Bottom** take the places away.

In a lab laid out by hand, the links are straight lines, and a line can pass
behind a brick in its way. **Curved Links**, in the menu, has Graphviz route
them around the bricks instead, as in the layouts of Graphviz, and moves no
brick; the project keeps the choice. Two bricks too close for a link to pass
between them have their links routed around their icons, across their names.

The menu also has **Export as Image…**: a PNG, an SVG or a PDF file of the
picture at 100%, on white, whatever the zoom and the theme. Exported to the folder of the
project, the picture can show in its README; see [](readme).
