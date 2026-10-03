Feature: Settings
  The Settings window, in the menu File: the settings of the application,
  which settings.toml keeps, and those of the open project, which its
  project.toml keeps.

  Scenario: A switch of the application turned off in the Settings window is off in settings.toml, and at the next start
    Given Virtualbricks is running
    When I turn off "Enable systray" in the Settings window, on its page Application
    Then settings.toml has
      | Setting   | Value |
      | tray_icon | false |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    When I start Virtualbricks again
    And I open the Settings window
    Then the page Application of the Settings window has "Enable systray" off

  Scenario: A switch of the project turned on in the Settings window is on in its project.toml
    Given Virtualbricks is running
    When I turn on "Allow female plugs on devices" in the Settings window, on its page This project
    Then project.toml has the settings
      | Setting            | Value |
      | allow_female_plugs | true  |
