@pictures
Feature: The pictures of the user guide
  Each scenario takes a picture of docs/guide/figures/, which a page of the
  guide shows: pytest --pictures -m pictures takes them there, and any
  other run lists those that differ. They run in the default workspace, so
  that the title of the main window names the project alone.

  Background:
    Given the workspace is the default one

  @needs-qemu-img @needs-qemu-system-i386 @needs-vde_switch
  Scenario: The first lab: sw1, and vm1 plugged into it, both running
    Given the empty disk image debian.qcow2 of 1 GB, in my home folder
    And Virtualbricks is running
    When I add an existing image, debian.qcow2 of my home folder, with the name it suggests, debian
    And I open the tab Bricks
    And I add the switch sw1
    And I add the virtual machine vm1
    And I connect vm1 to sw1, with Connect To in its menu
    And I turn on "No display" in the settings of vm1, on its page Display
    And I give vm1 the image debian, on its disk hda
    And I start vm1
    Then sw1 is running
    And the picture first-lab shows the main window

  Scenario: New Brick, open over the Bricks tab
    Given Virtualbricks is running
    When I add the switch sw1
    And I click the button "New Brick"
    Then the picture new-brick shows the main window

  Scenario: The settings of a switch, in place of the list
    Given Virtualbricks is running
    When I add the switch sw1
    And I open the settings of sw1
    Then the picture switch-settings shows the main window

  @needs-qemu-system-i386
  Scenario: The settings of a virtual machine, on its page Machine
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the virtual machine vm1
    And I connect vm1 to sw1, with Connect To in its menu
    And I open the settings of vm1, on its page Machine
    Then the picture machine-settings shows the main window

  @needs-qemu-img @needs-qemu-system-i386
  Scenario: The Images tab: debian, which vm1 and vm2 use, vm1 running, and scratch, which no disk uses
    Given the empty disk image debian.qcow2 of 1 GB, in my home folder
    And the files of my home folder were last changed on 2024-08-02
    And Virtualbricks is running
    When I add an existing image, debian.qcow2 of my home folder, used where it is, with the name it suggests, debian
    And I add a new empty disk, scratch, of 20 MB in the format raw
    And I open the tab Bricks
    And I add the virtual machine vm1
    And I add the virtual machine vm2
    And I turn on "No display" in the settings of vm1, on its page Display
    And I give vm1 the image debian, on its disk hda
    And I give vm2 the image debian, on its disk hda
    And I start vm1
    And I open the tab Images
    Then the picture images shows the main window

  @needs-qemu-img @needs-qemu-system-i386
  Scenario: The details of debian, which vm1 and vm2 use, vm1 running
    Given the empty disk image debian.qcow2 of 1 GB, in my home folder
    And the files of my home folder were last changed on 2024-08-02
    And Virtualbricks is running
    When I add an existing image, debian.qcow2 of my home folder, used where it is, with the name it suggests, debian
    And I add a new empty disk, scratch, of 20 MB in the format raw
    And I open the tab Bricks
    And I add the virtual machine vm1
    And I add the virtual machine vm2
    And I turn on "No display" in the settings of vm1, on its page Display
    And I give vm1 the image debian, on its disk hda
    And I give vm2 the image debian, on its disk hda
    And I start vm1
    And I open the details of debian
    Then the picture image-details shows the main window

  Scenario: The settings of an event that starts sw1 after 5 seconds
    Given Virtualbricks is running
    When I add the switch sw1
    And I make an event that starts sw1 after 5 seconds, with the name it suggests, new_event
    And I open the settings of the event new_event
    Then the picture event-settings shows the main window

  @needs-qemu-system-i386
  Scenario: The Events tab, with the events of the examples of the guide
    Given the project new_project has the project.toml
      """
      format = 1

      [events.clients]
      delay = 30
      actions = [
          {kind = "start", target = "vm2"},
          {kind = "start", target = "vm3"},
      ]

      [events.link_down]
      delay = 30
      actions = [
          {kind = "stop", target = "wire1"},
          {kind = "start", target = "link_up"},
      ]

      [events.link_up]
      delay = 30
      actions = [
          {kind = "start", target = "wire1"},
          {kind = "start", target = "link_down"},
      ]

      [events.tap1_up]
      delay = 2
      actions = [
          {kind = "shell", command = "sudo -A ip addr add 10.0.0.254/24 dev tap1 && sudo -A ip link set tap1 up"},
      ]

      [bricks.sw1]
      type = "switch"

      [bricks.sw2]
      type = "switch"

      [bricks.wire1]
      type = "wire"
      endpoints = ["sw1", "sw2"]

      [bricks.tap1]
      type = "tap"
      on_start = "tap1_up"
      connect = "sw1"

      [bricks.vm1]
      type = "qemu"
      on_start = "clients"
      nics = [{kind = "plug", connect = "sw1", mac = "52:54:00:12:34:01"}]

      [bricks.vm2]
      type = "qemu"
      nics = [{kind = "plug", connect = "sw2", mac = "52:54:00:12:34:02"}]

      [bricks.vm3]
      type = "qemu"
      nics = [{kind = "plug", connect = "sw2", mac = "52:54:00:12:34:03"}]
      """
    And Virtualbricks is running
    When I open the tab Events
    Then the picture events shows the main window

  Scenario: When It Starts, open in the menu of tap1
    Given the project new_project has the project.toml
      """
      format = 1

      [events.tap1_up]
      delay = 2
      actions = [
          {kind = "shell", command = "sudo -A ip addr add 10.0.0.254/24 dev tap1 && sudo -A ip link set tap1 up"},
      ]

      [bricks.sw1]
      type = "switch"

      [bricks.tap1]
      type = "tap"
      on_start = "tap1_up"
      connect = "sw1"
      """
    And Virtualbricks is running
    When I open the tab Bricks
    And I open When It Starts, in the menu of tap1
    Then the picture when-it-starts shows the main window

  @needs-qemu-system-i386 @needs-vde_switch
  Scenario: The Topology tab: sw1 and sw2 running, joined by wire1, with tap1 and three machines
    Given the project new_project has the project.toml
      """
      format = 1

      [bricks.sw1]
      type = "switch"

      [bricks.sw2]
      type = "switch"

      [bricks.wire1]
      type = "wire"
      endpoints = ["sw1", "sw2"]

      [bricks.tap1]
      type = "tap"
      connect = "sw1"

      [bricks.vm1]
      type = "qemu"
      nics = [{kind = "plug", connect = "sw1", mac = "52:54:00:12:34:01"}]

      [bricks.vm2]
      type = "qemu"
      nics = [{kind = "plug", connect = "sw2", mac = "52:54:00:12:34:02"}]

      [bricks.vm3]
      type = "qemu"
      nics = [{kind = "plug", connect = "sw2", mac = "52:54:00:12:34:03"}]
      """
    And Virtualbricks is running
    When I open the tab Bricks
    And I start sw1
    And I start sw2
    And I open the tab Topology
    Then the picture topology shows the main window

  @needs-qemu-system-i386 @needs-vde_switch
  Scenario: The menu of the picture of the lab, open
    Given the project new_project has the project.toml
      """
      format = 1

      [bricks.sw1]
      type = "switch"

      [bricks.sw2]
      type = "switch"

      [bricks.wire1]
      type = "wire"
      endpoints = ["sw1", "sw2"]

      [bricks.tap1]
      type = "tap"
      connect = "sw1"

      [bricks.vm1]
      type = "qemu"
      nics = [{kind = "plug", connect = "sw1", mac = "52:54:00:12:34:01"}]

      [bricks.vm2]
      type = "qemu"
      nics = [{kind = "plug", connect = "sw2", mac = "52:54:00:12:34:02"}]

      [bricks.vm3]
      type = "qemu"
      nics = [{kind = "plug", connect = "sw2", mac = "52:54:00:12:34:03"}]
      """
    And Virtualbricks is running
    When I open the tab Bricks
    And I start sw1
    And I start sw2
    And I open the menu of the picture of the lab
    Then the picture topology-menu shows the main window

  Scenario: The Readme tab, with a heading, a list and a link
    Given the project new_project has the README
      """
      # A lab of two machines

      Two machines on **one switch**, to try the *network* between them.

      - vm1: 10.0.0.1
      - vm2: 10.0.0.2

      The images are those of [Debian](https://www.debian.org/).
      """
    And Virtualbricks is running
    When I open the tab Readme
    Then the picture readme shows the main window

  Scenario: The editor of the Readme tab, with its syntax open
    Given the project new_project has the README
      """
      # A lab of two machines

      Two machines on **one switch**, to try the *network* between them.

      - vm1: 10.0.0.1
      - vm2: 10.0.0.2

      The images are those of [Debian](https://www.debian.org/).
      """
    And Virtualbricks is running
    When I open the syntax of the README, in its editor
    Then the picture readme-edit shows the main window

  Scenario: The Projects window, with two projects
    Given Virtualbricks is running
    When I add the switch sw1
    And I open the Projects window
    And I make a new project with the name it suggests, new_project-2
    And the projects were last saved on 2024-08-02
    And I open the Projects window
    Then the picture projects shows the Projects window

  Scenario: The Export window, before Export
    Given Virtualbricks is running
    When I add the switch sw1
    And I open the Export window
    Then the picture export shows the Export window

  Scenario: The Settings window, on its page This computer
    Given Virtualbricks is running
    When I open the Settings window
    Then the picture settings shows the Settings window

  @needs-vde_switch
  Scenario: The Logs window, once sw1 started and sudo refused to start tap1
    Given the messages start on 2024-08-02 at 10:00:00
    And sudo can't ask for the password
    And the project new_project has the project.toml
      """
      format = 1

      [bricks.sw1]
      type = "switch"

      [bricks.tap1]
      type = "tap"
      connect = "sw1"
      """
    And Virtualbricks is running
    When I quit Virtualbricks
    Then Virtualbricks has quit
    When I start Virtualbricks again
    And I start sw1
    And I try to start tap1
    And I close the error
    And I open the messages window
    And I filter the messages window with "level:warning"
    Then the picture logs shows the Logs window

  Scenario: The menu Projects, open
    Given Virtualbricks is running
    When I open the menu "Projects"
    Then the picture import-menu shows the main window

  @needs-qemu-img
  Scenario: The file chooser of Import…, on the archive of DTN2hops
    Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, with the private disks of its machines, in my Downloads folder
    And the files of my Downloads folder were last changed on 2024-08-02
    And Virtualbricks is running
    When I choose Import… in the menu Projects
    And in the file chooser, I select DTN2hops_26_Feb_2026.vbp of my Downloads folder
    Then the picture import-archive shows the file chooser

  @needs-qemu-img
  Scenario: The Import window, with the archive of DTN2hops, which hasn't its image
    Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, with the private disks of its machines, in my Downloads folder
    And Virtualbricks is running
    When I choose the archive DTN2hops_26_Feb_2026.vbp of my Downloads folder in the Import window, which suggests the name DTN2hops_26_Feb_2026
    Then the picture import shows the Import window

  @needs-qemu-img
  Scenario: The file chooser of the image of DTN2hops, on its file
    Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, with the private disks of its machines, in my Downloads folder
    And the empty disk image debian13.qcow2 of 1 GB, in my Downloads folder
    And the files of my Downloads folder were last changed on 2024-08-02
    And Virtualbricks is running
    When I choose the archive DTN2hops_26_Feb_2026.vbp of my Downloads folder in the Import window, which suggests the name DTN2hops_26_Feb_2026
    And I click the radio button "Use a file…"
    And in the file chooser, I select debian13.qcow2 of my Downloads folder
    Then the picture import-image shows the file chooser

  @needs-qemu-img
  Scenario: The Import window, with the archive of DTN2hops and the file of its image
    Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, with the private disks of its machines, in my Downloads folder
    And the empty disk image debian13.qcow2 of 1 GB, in my Downloads folder
    And Virtualbricks is running
    When I choose the archive DTN2hops_26_Feb_2026.vbp of my Downloads folder in the Import window, which suggests the name DTN2hops_26_Feb_2026
    And in the Import window, I use the file debian13.qcow2 of my Downloads folder for the image debian13
    Then the picture import-ready shows the Import window

  @needs-qemu-img
  Scenario: The Import window, while it imports DTN2hops
    Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, with the private disks of its machines, in my Downloads folder
    And the empty disk image debian13.qcow2 of 1 GB, in my Downloads folder
    And the extraction of an archive stops after its first 1 MiB, until I let it go on
    And Virtualbricks is running
    When I choose the archive DTN2hops_26_Feb_2026.vbp of my Downloads folder in the Import window, which suggests the name DTN2hops_26_Feb_2026
    And in the Import window, I use the file debian13.qcow2 of my Downloads folder for the image debian13
    And I click the button "Import"
    Then the label "Extracting the archive" shows
    And the picture import-progress shows the Import window
    When I let the extraction go on
    Then the main window shows the project DTN2hops_26_Feb_2026

  @needs-qemu-img
  Scenario: The main window, once DTN2hops is imported
    Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, with the private disks of its machines, in my Downloads folder
    And the empty disk image debian13.qcow2 of 1 GB, in my Downloads folder
    And Virtualbricks is running
    When I choose the archive DTN2hops_26_Feb_2026.vbp of my Downloads folder in the Import window, which suggests the name DTN2hops_26_Feb_2026
    And in the Import window, I use the file debian13.qcow2 of my Downloads folder for the image debian13
    And I import the archive chosen in the Import window
    Then the picture import-done shows the main window
