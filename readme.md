ProtonVPN Accessibility for NVDA

Author: Mama Sene
Contact: tech.access33@gmail.com

Download stable version
Source code on GitHub

NVDA compatibility:
- Minimum version: 2025.1
- Tested with: NVDA 2026.3

Presentation

This add-on improves the accessibility of the ProtonVPN Windows application for NVDA users.

Features include:
- Proper labeling of interface elements, including the country list
- Dynamic spoken information about VPN status
- NetShield, Kill Switch, Split tunneling and Port forwarding announced by name, with their state wherever ProtonVPN publishes it
- Quick access to the country search field
- A searchable list of every country and city on display
- Keyboard shortcuts for common VPN actions
- Multilingual support (English and French)

The add-on can announce:
- IP address
- Country
- VPN provider
- Traffic information
- Connection status

Usage

Once the add-on is installed, simply open ProtonVPN.

The add-on automatically enhances:
- Buttons and controls labeling
- Connection status announcements
- Traffic and network information
- Accessibility of dynamic UI elements

Keyboard Shortcuts

- Control+Shift+D: Connect / Disconnect VPN
- Control+Shift+K: Toggle Kill Switch
- Control+Shift+T: Announce traffic information
- Control+Shift+L: Search for a country in the ProtonVPN field
- Control+Shift+O: List countries and cities
- Control+Shift+F10: Describe the focused control

All shortcuts can be reassigned from NVDA's Input Gestures dialog,
under the ProtonVPN category.

Countries and cities

Control+Shift+O opens the list of countries and cities ProtonVPN is currently
showing. Type a few letters to filter: the filter covers the country as well as
the city, so both "south" and "johan" reach Johannesburg. Press Enter to connect
to the row you picked.

A country that holds cities says how many. To see its cities in the ProtonVPN
window, expand it as usual; the add-on then reads them in the order they are
displayed.

ProtonVPN only builds the rows that are visible on screen, so the add-on's list
mirrors what is on display. To reach a country that is not there, use
Control+Shift+L, which filters the full list.

Reporting a problem

If something in ProtonVPN is announced incorrectly, press Control+Shift+F9 in
the ProtonVPN window: the add-on writes diagnostics to the NVDA log. Attach that
log to your report, it will help get the problem fixed.

For one specific control that is unlabelled or announced wrongly, move to it and
press Control+Shift+F10. The add-on describes it in the log and copies that
description to the clipboard, so you can paste it straight into your report. It
includes the control's identifier, its type, the name the application gives it,
the name the add-on announces, and what the control actually contains.

IP addresses are masked before being written.

Notes

The spoken messages (IP address, country, provider, traffic) are dynamic.
They depend on the current VPN connection state and available data provided by ProtonVPN.

This add-on does not send any data and works entirely locally.

This is a community add-on and is not affiliated with Proton AG.

Changes

Version 2.0.0

ProtonVPN can now be used from end to end with NVDA: the cities are covered, every control says what it is, and the Kill Switch really switches.

New features
- The cities are there. Control+Shift+O opens a searchable list of every country and city on display, and each city is announced with the country it belongs to.
- Control+Shift+L takes you to the ProtonVPN search field, to reach a country in a few letters.
- Control+Shift+K turns the Kill Switch on and off, then tells you the state it reads back from it. In the right-hand column it announces its name alone: ProtonVPN does not publish its state there.
- Control+Shift+T announces the connection: traffic, server load, VPN address and protocol.
- Control+Shift+D connects and disconnects, and says so only once it has really happened.
- Two shortcuts help with a bug report: Control+Shift+F9 writes a diagnostic to the NVDA log, and Control+Shift+F10 describes the control you are on.

Fixes
- NVDA no longer crashes when you open the cities of a country.
- Each city is announced under its own country, and the list follows the order on screen.
- The country you are connected to is in the list, and says that it is connected.
- Buttons, check boxes and radio buttons that announced nothing now have a name, in the main window as well as in the settings.
- Internal names are no longer read out loud, neither as a name nor as the value of a drop-down list.
- The add-on speaks French.
- Your IP address and your account address no longer reach the NVDA log, which is the file you attach to a bug report.
- A shortcut that pressed the wrong button has been removed, and the Kill Switch can no longer be mistaken for another protection.

Improvements
- Moving through the interface answers straight away. Going down the country list no longer makes NVDA lag, and the shortcuts answer without waiting.
- Tested with NVDA 2026.3.

Version 1.0.1
- Updated add-on display name for international users
- Fixed project repository URL
- Improved manifest metadata
- Updated French translation metadata

Version 1.0.0
- Initial stable release  
- Added NVDA 2026.1 compatibility
- Added Python 3.13 compatibility
- Improved ProtonVPN interface accessibility
- Added keyboard shortcuts
- Added dynamic announcements for VPN status
- Added multilingual documentation support
- Added French translations
