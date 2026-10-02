Feature: Migration
  At its first start, Virtualbricks migrates the settings and the projects
  of Virtualbricks 2.1, and opens the project that was open last.

  Background:
    Given the project DTN2hops_26_Feb_2026 of Virtualbricks 2.1
    And the settings of Virtualbricks 2.1, with DTN2hops_26_Feb_2026 open last

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
      | switchwrapper        | Switch wrapper · /var/run/switch/sck                                               | Not configured |
      | sw5                  | Switch · 32 ports                                                                  | Stopped        |
      | channel_emulator     | Netemu · sw1 ↔ sw2 · 10 ms                                                         | Stopped        |
      | sat_channel_emulator | Netemu · sw3 ↔ sw4 · 20 ms                                                         | Stopped        |
      | to_host_ch_emulator  | Netemu · sw5 ↔ switchwrapper · 5/0% loss                                           | Stopped        |
      | node1                | Virtual machine · x86_64 · KVM · 1508 MiB · eth0 on switchwrapper · eth1 on sw1    | Stopped        |
      | node2                | Virtual machine · x86_64 · KVM · 500 MiB · eth0 on sw5 · eth1 on sw2 · eth2 on sw3 | Stopped        |
      | node3                | Virtual machine · x86_64 · KVM · 500 MiB · eth0 on switchwrapper · eth1 on sw1     | Stopped        |
      | node4                | Virtual machine · x86_64 · KVM · 500 MiB · eth0 on switchwrapper · eth1 on sw4     | Stopped        |
