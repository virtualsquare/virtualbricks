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
