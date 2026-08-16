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
- Proper labeling of interface elements
- Dynamic spoken information about VPN status
- Accessibility improvements for UI Automation controls
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

Notes

The spoken messages (IP address, country, provider, traffic) are dynamic.
They depend on the current VPN connection state and available data provided by ProtonVPN.

This add-on does not send any data and works entirely locally.

This is a community add-on and is not affiliated with Proton AG.

Changes

Version 1.0.2
- Fixed the French translation, which was not being applied: the add-on speaks French again on French installations
- The Kill Switch shortcut now identifies the Kill Switch before acting, and announces whether it ended up enabled or disabled. It can no longer change another setting by mistake
- The right-hand widgets are now named after what they display instead of their position, and NVDA announces whether each one is enabled or disabled
- The connection shortcut no longer risks activating an unrelated button, and it now reports when the VPN state did not actually change
- IP addresses are no longer written to the NVDA log, which is often attached to bug reports
- Buttons and switches are activated more reliably, and NVDA no longer risks freezing while ProtonVPN is connecting
- Faster response when moving through the ProtonVPN window
- The license file is now included in the package, and the version history is shown in the Add-on Store
- Add-on summary, description and version history are now available in French

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
