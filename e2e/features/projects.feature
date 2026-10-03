Feature: Projects
  The projects of the workspace, each a folder with its project.toml: the
  Projects window makes them, opens them and looks after them.

  Scenario: A new project made in the Projects window, with the name it suggests, opens
    Given Virtualbricks is running
    When I open the Projects window
    And I make a new project with the name it suggests, new_project-2
    Then the main window shows the project new_project-2
    And the folder of new_project-2 has project.toml
