@pictures
Feature: The pictures of the user guide
  Each scenario takes a picture of help/C/figures/, which a page of the
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

  @needs-qemu-img
  Scenario: The Images tab, with one image
    Given the empty disk image debian.qcow2 of 1 GB, in my home folder
    And Virtualbricks is running
    When I add an existing image, debian.qcow2 of my home folder, with the name it suggests, debian
    Then the picture images shows the main window

  Scenario: The settings of an event that starts sw1 after 5 seconds
    Given Virtualbricks is running
    When I add the switch sw1
    And I make an event that starts sw1 after 5 seconds, with the name it suggests, new_event
    And I open the settings of the event new_event
    Then the picture event-settings shows the main window

  @needs-qemu-system-i386
  Scenario: The Topology tab: sw1, and vm1 plugged into it
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the virtual machine vm1
    And I connect vm1 to sw1, with Connect To in its menu
    And I open the tab Topology
    Then the picture topology shows the main window

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

  Scenario: The Import window, with the archive of a lab without its image
    Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, in my home folder
    And Virtualbricks is running
    When I choose the archive DTN2hops_26_Feb_2026.vbp of my home folder in the Import window, which suggests the name DTN2hops_26_Feb_2026
    Then the picture import shows the Import window
