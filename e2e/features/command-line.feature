Feature: Command line and sockets
  Virtualbricks started with options, and another one beside it, in the
  same workspace: one that sends it a command, one that opens its windows,
  one that its lock keeps out.

  @needs-vde_switch
  Scenario: A switch started with --command runs, and the windows show it
    Given Virtualbricks is running with --listen
    When I add the switch sw1
    And I run virtualbricks --command brick start sw1
    Then sw1 is running
    When I stop sw1
    Then sw1 is stopped

  @needs-vde_switch
  Scenario: The windows of another Virtualbricks start a switch there, and close without stopping it
    Given another Virtualbricks runs with --no-gui --listen
    And Virtualbricks is running with --connect
    Then the main window shows the project new_project on this computer
    When I add the switch sw1
    And I start sw1
    Then sw1 is running
    And sw1 runs in the other Virtualbricks
    When I quit Virtualbricks
    Then Virtualbricks has quit
    And sw1 runs in the other Virtualbricks

  @needs-vde_switch
  Scenario: A second Virtualbricks in the same workspace exits, saying why, and the first goes on
    Given Virtualbricks is running with --lock workspace
    When I add the switch sw1
    And I start sw1
    And I start another Virtualbricks with --lock workspace
    Then the other Virtualbricks exits with 1, saying "Another Virtualbricks is running in the workspace ~/workspace: start this one in another, with --workspace."
    And the other Virtualbricks names the process of Virtualbricks
    And Virtualbricks hasn't quit
    And sw1 is still running
