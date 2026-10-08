Feature: Migration
  At its start, Virtualbricks migrates the projects of Virtualbricks 2.1 in
  its workspace; at the first start, the settings of 2.1 too.

  Background:
    Given the project DTN2hops_26_Feb_2026 of Virtualbricks 2.1

  Rule: The first start migrates the settings too, and opens the project
    that was open last

    Background:
      Given the settings of Virtualbricks 2.1, with DTN2hops_26_Feb_2026 open last

    Scenario: An old project is migrated at the first start
      When I start Virtualbricks for the first time
      Then the migration window shows
      And the migration window lists
        | Project              | Bricks | Status      |
        | .virtualbricks.conf  | —      | ✓ Migrated  |
        | DTN2hops_26_Feb_2026 | 13     | ⚠ 1 warning |
      And DTN2hops_26_Feb_2026 is migrated
      When I close the migration window
      Then the main window shows the project DTN2hops_26_Feb_2026
      And the list of bricks has
        | Brick                | Detail                                                                             | State          |
        | sw1                  | Switch · 32 ports                                                                  | Stopped        |
        | sw2                  | Switch · 32 ports                                                                  | Stopped        |
        | sw3                  | Switch · 32 ports                                                                  | Stopped        |
        | sw4                  | Switch · 32 ports                                                                  | Stopped        |
        | switchwrapper        | Switch wrapper · /var/run/switch/sck                                               | Stopped        |
        | sw5                  | Switch · 32 ports                                                                  | Stopped        |
        | channel_emulator     | Netemu · sw1 ↔ sw2 · 10 ms                                                         | Stopped        |
        | sat_channel_emulator | Netemu · sw3 ↔ sw4 · 20 ms                                                         | Stopped        |
        | to_host_ch_emulator  | Netemu · sw5 ↔ switchwrapper · 5/0% loss                                           | Stopped        |
        | node1                | Virtual machine · x86_64 · KVM · 1508 MiB · eth0 on switchwrapper · eth1 on sw1    | Stopped        |
        | node2                | Virtual machine · x86_64 · KVM · 500 MiB · eth0 on sw5 · eth1 on sw2 · eth2 on sw3 | Stopped        |
        | node3                | Virtual machine · x86_64 · KVM · 500 MiB · eth0 on switchwrapper · eth1 on sw1     | Stopped        |
        | node4                | Virtual machine · x86_64 · KVM · 500 MiB · eth0 on switchwrapper · eth1 on sw4     | Stopped        |

    Scenario: The next start doesn't migrate again
      Given Virtualbricks migrated DTN2hops_26_Feb_2026 at its first start
      When I quit Virtualbricks
      Then Virtualbricks has quit
      When I start Virtualbricks again
      Then the main window shows the project DTN2hops_26_Feb_2026
      And the migration window doesn't show

    @needs-vde_switch @needs-wirefilter
    Scenario: Two switches of a migrated project and the link between them run
      Given Virtualbricks migrated DTN2hops_26_Feb_2026 at its first start
      When I start sw1
      And I start sw2
      And I start channel_emulator
      Then sw1 is running
      And sw2 is running
      And channel_emulator is running
      When I stop channel_emulator
      And I stop sw2
      And I stop sw1
      And I quit Virtualbricks
      Then Virtualbricks has quit

    Scenario: The report of the migration, saved to a file, has its rows and their messages
      When I start Virtualbricks for the first time
      Then DTN2hops_26_Feb_2026 is migrated
      When I save the report of the migration to report.txt of my home folder, typing its path
      Then the file report.txt of my home folder has
        """
        .virtualbricks.conf   migrated
        DTN2hops_26_Feb_2026  migrated   1 warning

        DTN2hops_26_Feb_2026
          warning   .project:1  [Image:debian13] /home/carlo/VB_images/debian13.qcow2 not found, kept in the library

        1 of 1 projects migrated.
        """

    Scenario: A migration closed while it runs keeps what it migrated, and migrates the rest at the next start; the project open last isn't saved
      Given the projects lab01 to lab40 of Virtualbricks 2.1, copies of DTN2hops_26_Feb_2026
      When I start Virtualbricks for the first time
      And I close the migration window while it migrates
      Then the main window shows the project new_project
      When I quit Virtualbricks
      Then Virtualbricks has quit
      And some of the projects are migrated, and the others not
      When I start Virtualbricks again
      Then the migration window shows
      And the projects not migrated before are migrated, and the others stay as they were

  Rule: A project of 2.1 copied into the workspace is migrated at the next
    start, and the project open last stays open

    Scenario: An old project copied into the workspace is migrated
      When I start Virtualbricks again
      Then the migration window shows
      And the migration window lists
        | Project              | Bricks | Status      |
        | DTN2hops_26_Feb_2026 | 13     | ⚠ 1 warning |
      And DTN2hops_26_Feb_2026 is migrated
      When I close the migration window
      Then the main window shows the project new_project

    Scenario: An old project that can't be converted fails, says why, and stays as it was
      Given the project lab of Virtualbricks 2.1, whose .project is
        """
        [Switch:sw1]
        numports=32

        [Switch:sw1]
        numports=16
        """
      When I start Virtualbricks again
      Then the migration window lists
        | Project              | Bricks | Status      |
        | DTN2hops_26_Feb_2026 | 13     | ⚠ 1 warning |
        | lab                  | —      | ✗ Failed    |
      When I select lab in the migration window
      Then the migration window shows the error of lab: ".project:4 [Switch:sw1] defined twice (first at line 1); project not migrated"
      And lab isn't migrated
      And the old file lab/.project of the workspace stays as it was

    Scenario: An old project that is a single file in the workspace becomes a folder with its project.toml
      Given the project DTN2hops_26_Feb_2026 of Virtualbricks 2.1, as the single file lab.vbl in the workspace
      When I start Virtualbricks again
      Then the migration window lists
        | Project              | Bricks | Status      |
        | DTN2hops_26_Feb_2026 | 13     | ⚠ 1 warning |
        | lab                  | 13     | ⚠ 1 warning |
      And lab is migrated
      And the folder of lab has project.toml
      And the old file lab.vbl of the workspace stays as it was
