ProtonVPN Accessibility for NVDA

Author: Mama Sene
Contact: tech.access33@gmail.com

Download stable version
Source code on GitHub

NVDA compatibility:
- Minimum NVDA version: 2025.1
- Last tested NVDA version: 2026.3.1

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
- Two shortcuts help with a bug report: Control+Shift+F9 writes a diagnostic to the NVDA log, and Control+Shift+F10 describes the control you are on.

Changes
- Control+Shift+K turns the Kill Switch on and off. It used to stop at its settings page, without even placing the cursor on the switch. In the right-hand column it announces its name alone: ProtonVPN does not publish its state there.
- Control+Shift+T announces the whole connection panel, traffic, server load, VPN address and protocol, instead of two values chosen in advance.
- The Control+Shift+C shortcut is gone. It claimed to open a country selector and pressed whichever unnamed button came second in the connection card.

Fixes
- NVDA no longer crashes when you open the cities of a country.
- Each city is announced under its own country, and the list follows the order on screen.
- The country you are connected to is in the list, and says that it is connected.
- Buttons, check boxes and radio buttons that announced nothing now have a name, in the main window as well as in the settings.
- Internal names are no longer read out loud, neither as a name nor as the value of a drop-down list.
- Nothing that identifies you reaches the NVDA log, the file you attach to a bug report: your account address is masked, as your IP address already was.
- The Kill Switch can no longer be mistaken for another protection.

Improvements
- Moving through the interface answers straight away. Going down the country list no longer makes NVDA lag, and the shortcuts answer without waiting.
- Tested with NVDA 2026.3.1.

Version 1.1.0

New features
- Search for a country with Control+Shift+L: the add-on takes you straight to the ProtonVPN search field. Type a few letters to reach any country.
- The country list is now readable: each country is announced by its name.
- The country list tabs (All countries, Secure Core, P2P, Tor) are announced by their name.
- NetShield, Kill Switch, Split tunneling and Port forwarding are announced by name, together with whether each one is on or off.

Fixes
- The add-on now speaks French.
- The Kill Switch, traffic and country shortcuts work again, including while the VPN is connected.
- Connection and disconnection are announced only once they have actually happened, and the add-on tells you if nothing changed.

Improvements
- Keyboard shortcuts respond much faster.
- NVDA no longer freezes while ProtonVPN is establishing a connection.
- Your IP address is no longer recorded in the NVDA log.
- The add-on summary, description and version history are available in French.

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
