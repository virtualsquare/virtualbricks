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
