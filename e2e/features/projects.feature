Feature: Projects
  The projects of the workspace, each a folder with its project.toml: the
  Projects window makes them, opens them and looks after them.

  Scenario: A new project made in the Projects window, with the name it suggests, opens
    Given Virtualbricks is running
    When I open the Projects window
    And I make a new project with the name it suggests, new_project-2
    Then the main window shows the project new_project-2
    And the folder of new_project-2 has project.toml

  Scenario: Another project opened from the Projects window shows its bricks
    Given Virtualbricks is running
    When I add the switch sw1
    And I open the Projects window
    And I make a new project with the name it suggests, new_project-2
    And I add the wire w1
    And I open the Projects window
    And I open the project new_project
    Then the main window shows the project new_project
    And the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |

  @needs-vde_switch
  Scenario: Another project doesn't open while a brick runs, and the brick still runs
    Given Virtualbricks is running
    When I open the Projects window
    And I make a new project with the name it suggests, new_project-2
    And I add the switch sw1
    And I start sw1
    And I open the Projects window
    And I try to open the project new_project
    Then an error says "Cannot open the project "new_project": Project cannot be closed: there are running bricks"
    When I close the error
    Then the Projects window says "Cannot open new_project: Project cannot be closed: there are running bricks"
    And the main window shows the project new_project-2
    And sw1 is still running

  Scenario: The project opened last opens at the next start
    Given Virtualbricks is running
    When I open the Projects window
    And I make a new project with the name it suggests, new_project-2
    And I add the switch sw1
    And I open the Projects window
    And I make a new project with the name it suggests, new_project-3
    And I open the Projects window
    And I open the project new_project-2
    And I quit Virtualbricks
    Then Virtualbricks has quit
    When I start Virtualbricks again
    Then the main window shows the project new_project-2
    And the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |

  Scenario: A project duplicated with the name it suggests is a copy of the other, and opens
    Given Virtualbricks is running
    When I add the switch sw1
    And I open the Projects window
    And I duplicate the project new_project with the name it suggests, new_project-copy
    Then the main window shows the project new_project-copy
    And the folder of new_project-copy is a copy of that of new_project
    And the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |

  Scenario: An archive of Virtualbricks 2.1 is converted at its import, and opens
    Given the archive DTN2hops_26_Feb_2026.vbp of Virtualbricks 2.1, in my home folder
    And Virtualbricks is running
    When I import the archive DTN2hops_26_Feb_2026.vbp of my home folder with the name it suggests, DTN2hops_26_Feb_2026
    Then the main window shows the project DTN2hops_26_Feb_2026
    And the folder of DTN2hops_26_Feb_2026 has project.toml
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

  Scenario: A project exported to an archive, then imported with the name it suggests, has its bricks
    Given Virtualbricks is running
    When I add the switch sw1
    And I export the project to new_project.vbp of my home folder
    Then the archive new_project.vbp of my home folder has the bricks
      | Brick | Type   |
      | sw1   | switch |
    When I import the archive new_project.vbp of my home folder, typing its path, with the name it suggests, new_project-2
    Then the main window shows the project new_project-2
    And the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |

  Scenario: A project removed from the Projects window goes to the trash, once confirmed
    Given Virtualbricks is running
    When I open the Projects window
    And I make a new project with the name it suggests, new_project-2
    And I open the Projects window
    And I remove the project new_project, and move it to the trash
    Then the Projects window doesn't list new_project
    And the folder of new_project is in the trash

  Scenario: A project removed from a workspace on a drive without a trash is deleted for good, once confirmed
    Given the workspace is on a drive without a trash
    And Virtualbricks is running
    When I open the Projects window
    And I make a new project with the name it suggests, new_project-2
    And I open the Projects window
    And I remove the project new_project, which can't go to the trash, and delete it permanently
    Then the Projects window doesn't list new_project
    And the folder of new_project is deleted, and in no trash
