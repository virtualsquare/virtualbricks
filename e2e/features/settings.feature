Feature: Settings
  The Settings window, in the menu File: a page for the settings of this
  computer, which settings.toml keeps, and one for those of the open
  project, which its project.toml keeps.

  Scenario: A switch of this computer turned off in the Settings window is off in settings.toml, and at the next start
    Given Virtualbricks is running
    When I turn off "Tray icon" in the Settings window, on its page This computer
    Then settings.toml has
      | Setting   | Value |
      | tray_icon | false |
    When I quit Virtualbricks
    Then Virtualbricks has quit
    When I start Virtualbricks again
    And I open the Settings window
    Then the page This computer of the Settings window has "Tray icon" off

  Scenario: A switch of the project turned on in the Settings window is on in its project.toml
    Given Virtualbricks is running
    When I turn on "Plugs into machines" in the Settings window, on its page Project new_project
    Then project.toml has the settings
      | Setting            | Value |
      | allow_female_plugs | true  |

  Scenario: Cancel in the Settings window leaves the settings as they were, and settings.toml too
    Given Virtualbricks is running
    When I turn off "Tray icon" on the page This computer of the Settings window, then cancel
    And I open the Settings window
    Then the page This computer of the Settings window has "Tray icon" on
    And settings.toml is as it was

  Scenario: A VDE folder without a program that isn't on this computer names the program, with its package
    Given vde_cryptcab isn't on this computer
    And Virtualbricks is running
    When I type "/usr/local/bin" as "VDE folder" on the page Project new_project of the Settings window
    Then the row "VDE folder" of the Settings window says "Missing here and in PATH: vde_cryptcab (vde2-cryptcab)"

  @needs-qemu-system-x86_64
  Scenario: The menu of the audio driver has the drivers of QEMU, those that play sound first
    Given Virtualbricks is running
    When I open the Settings window
    Then the menu of "Audio driver" in the Settings window has the audio drivers of qemu-system-x86_64
