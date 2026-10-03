Feature: Bricks
  The bricks of a project start and stop, each with its processes.

  @needs-vde_switch
  Scenario: A switch runs for a while, then stops
    Given Virtualbricks is running
    When I add the switch sw1
    And I start sw1
    Then sw1 is running
    When I wait 5 seconds
    Then sw1 is still running
    When I stop sw1
    Then sw1 is stopped
    When I quit Virtualbricks
    Then Virtualbricks has quit

  @needs-vde_switch @needs-dpipe @needs-vde_plug
  Scenario: A wire joins two switches
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I join sw1 and sw2 with the wire w1
    Then the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |
      | sw2   | Switch · 32 ports | Stopped |
      | w1    | Wire · sw1 ↔ sw2  | Stopped |
    When I start sw1
    And I start sw2
    And I start w1
    Then w1 runs with the sockets of sw1 and sw2
    When I stop w1
    Then w1 is stopped
    When I stop sw2
    And I stop sw1
    And I quit Virtualbricks
    Then Virtualbricks has quit

  @needs-vde_switch @needs-dpipe @needs-vde_plug
  Scenario: Start All starts the bricks that can start, Stop All stops them
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I join sw1 and sw2 with the wire w1
    And I add the wire w2
    And I start all the bricks
    Then the list of bricks has
      | Brick | Detail                   | State         |
      | sw1   | Switch · 32 ports        | Running       |
      | sw2   | Switch · 32 ports        | Running       |
      | w1    | Wire · sw1 ↔ sw2         | Running       |
      | w2    | Wire · nothing ↔ nothing | Not connected |
    And sw1 is running
    And sw2 is running
    And w1 runs with the sockets of sw1 and sw2
    When I stop all the bricks
    Then no brick runs

  @needs-vde_switch
  Scenario: A switch wrapper runs on a switch that another program runs
    Given a switch that another program runs
    And Virtualbricks is running
    When I add the switch wrapper wr1
    Then wr1 is not configured
    When I give wr1 the control folder of that switch
    Then wr1 is stopped
    When I start wr1
    Then wr1 is running
    When I stop wr1
    Then wr1 is stopped
    And the switch that another program runs still runs

  Scenario: A switch wrapper without a control folder can't start, and its row says why
    Given Virtualbricks is running
    When I add the switch wrapper wr1
    Then the list of bricks has
      | Brick | Detail                     | State          |
      | wr1   | Switch wrapper · no socket | Not configured |
    And wr1 can't start: "Configure wr1 first"
    When I try to start wr1
    Then wr1 is not configured
    And no brick runs

  Scenario: A switch whose program fails at once shows the error and the output of the program
    Given a vde_switch that writes "no switch today" and exits with 3
    And Virtualbricks is running
    When I add the switch sw1
    And I try to start sw1
    Then an error says "Process terminated. process ended with exit code 3"
    And sw1 is stopped
    When I close the error
    And I open the messages window
    Then the messages window has the output of sw1: "no switch today"

  @needs-vde_switch
  Scenario: The buttons of the settings of a switch change its ports and its hub mode
    Given Virtualbricks is running
    When I add the switch sw1
    And I give sw1 34 ports and hub mode, with the buttons of its settings
    Then the list of bricks has
      | Brick | Detail                  | State   |
      | sw1   | Switch · 34 ports · hub | Stopped |
    When I start sw1
    Then sw1 runs with 34 ports, as a hub
    When I stop sw1
    Then sw1 is stopped

  Scenario: Cancel leaves the settings of a switch as they were
    Given Virtualbricks is running
    When I add the switch sw1
    And I give sw1 34 ports and hub mode in its settings, then cancel
    Then the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has sw1 with
      | Setting  | Value |
      | ports    | 32    |
      | hub_mode | false |

  Scenario: Escape leaves the settings of a switch as they were
    Given Virtualbricks is running
    When I add the switch sw1
    And I give sw1 34 ports and hub mode in its settings, then press Escape
    Then the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has sw1 with
      | Setting  | Value |
      | ports    | 32    |
      | hub_mode | false |

  Scenario: Duplicate copies a brick with its settings, under its name with the next free number
    Given Virtualbricks is running
    When I add the switch sw1
    And I give sw1 34 ports and hub mode, with the buttons of its settings
    And I duplicate sw1 from its menu
    And I duplicate sw1 from its menu
    Then the list of bricks has
      | Brick | Detail                  | State   |
      | sw1   | Switch · 34 ports · hub | Stopped |
      | sw2   | Switch · 34 ports · hub | Stopped |
      | sw3   | Switch · 34 ports · hub | Stopped |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has sw2 with the settings of sw1

  Scenario: Delete removes a brick, once confirmed
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I delete sw2 from its menu, and confirm
    Then the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the bricks
      | Brick | Type   |
      | sw1   | switch |

  @needs-vde_switch
  Scenario: The switch over the list shows only the running bricks, with their process
    Given Virtualbricks is running
    When I add the switch sw1
    And I add the switch sw2
    And I start sw1
    And I show only the running bricks
    Then the list of bricks shows only sw1, with its process
    When I show all the bricks
    Then the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Running |
      | sw2   | Switch · 32 ports | Stopped |

  @needs-vde_switch
  Scenario: Quit is refused while a switch runs, and the switch still runs
    Given Virtualbricks is running
    When I add the switch sw1
    And I start sw1
    And I quit Virtualbricks
    Then an error says "Cannot close virtualbricks: there are running bricks"
    When I close the error
    Then Virtualbricks hasn't quit
    And sw1 is still running

  Scenario: A switch added is in the project after a quit, and shows at the next start
    Given Virtualbricks is running
    When I add the switch sw1
    And I quit Virtualbricks
    Then Virtualbricks has quit
    And project.toml has the bricks
      | Brick | Type   |
      | sw1   | switch |
    When I start Virtualbricks again
    Then the main window shows the project new_project
    And the list of bricks has
      | Brick | Detail            | State   |
      | sw1   | Switch · 32 ports | Stopped |
