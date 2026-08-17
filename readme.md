ProtonVPN Accessibility for NVDA

Author: Mama Sene
Contact: tech.access33@gmail.com

Download stable version
Source code on GitHub

NVDA compatibility:
- Minimum version: 2025.1
- Tested with: NVDA 2026.1

Presentation

This add-on improves the accessibility of the ProtonVPN Windows application for NVDA users.

Features include:
- Proper labeling of interface elements, including the country list
- Dynamic spoken information about VPN status
- On/off state announced for NetShield, Kill Switch, Split tunneling and Port forwarding
- Quick access to the country search field
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
- Control+Shift+C: Open country selector
- Control+Shift+T: Announce traffic information
- Control+Shift+L: Search for a country
- Control+Shift+F9: Write diagnostics to the NVDA log

All shortcuts can be reassigned from NVDA's Input Gestures dialog,
under the ProtonVPN category.

Notes

The spoken messages (IP address, country, provider, traffic) are dynamic.
They depend on the current VPN connection state and available data provided by ProtonVPN.

This add-on does not send any data and works entirely locally.

This is a community add-on and is not affiliated with Proton AG.

Changes

Version 1.1.0

New features
- Search for a country with Control+Shift+L: the add-on takes you straight to the ProtonVPN search field, so you can reach any country by typing a few letters
- The country list is now readable: each country is announced by its name instead of an internal code
- NetShield, Kill Switch, Split tunneling and Port forwarding are announced by name, together with whether each one is on or off

Fixes
- The add-on now speaks French. The translation was not being applied at all
- The Kill Switch, traffic and country shortcuts work again, including while the VPN is connected
- The country shortcut now works while connected, by opening the server change panel
- The connection status is announced only once the change has actually happened, and the add-on now tells you when nothing changed

Improvements
- Keyboard shortcuts respond much faster
- NVDA no longer risks freezing while ProtonVPN is establishing a connection
- IP addresses are no longer written to the NVDA log, which is often attached to bug reports
- Add-on summary, description and version history are now available in French
- The license file now ships with the add-on

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
