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
