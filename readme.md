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
- On/off state announced for NetShield, Kill Switch, Split tunneling and Port forwarding
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

This version gathers everything done since 1.1.0: no more crash in the city list, the cities covered, labels read from what the application displays, the Kill Switch actually switched, and nothing that identifies you in the log. The entries below detail each step.

Improvements
- Moving through the interface answers faster. NVDA asks a control for its name, its description and its state again at every cycle - the braille display refreshing, the focus being re-read - and each of those asks used to re-read the whole contents of the control from ProtonVPN: for a country row and its cities, more than a hundred elements, several times a second, on a control that had not moved. What a control shows is now read at most twice a second. The state of a protection is still read from the control itself every single time it is announced.
- Naming a control no longer walks up the tree when its own identifier already says what it is. Close settings, Back, Account and the banner buttons each cost five round trips to the application, at every pass of the focus, for an answer that changed nothing.
- Walking the tree now carries the properties it needs with it. Each step used to be followed by one round trip per property read, so a five-level walk paid fifteen instead of five.
- Measured on the window layouts the diagnostics describe: a full pass of the focus over the eight kinds of control costs 14 round trips to ProtonVPN instead of 31, and an announcement read again on a control that has not moved costs 2 instead of 16. Those two are the state of a protection, which is read afresh every time it is announced.

Version 1.8.2

Fixes
- Control+Shift+K said the Kill Switch could not be found when the settings were open on another page, which sounded like a fault. In that state neither control is reachable: the right column has gone with its widgets, and the switch exists only on its own page. The add-on now says to go back first.
- The diagnostic took about eighteen seconds whenever no widget was found, which is the case as soon as the settings are open. It now details fewer buttons, and reads the contents only of those without a name, the only ones it learns anything from.

Version 1.8.1

Fixes
- The protocol announced itself as "Protocol: Protocol". Its descriptive text was recognised neither as the label nor as a value, so it stayed in both. The word "protocol" is now part of what the add-on reads as a label.
- The current traffic announced the graph's axis ticks instead of the measurements: "Current traffic: 30, 15" rather than "16 KB/s, 14 KB/s". Units had been listed among the words that mark a label, so a measurement carrying one was taken for a label and thrown away. A unit belongs to the measurement.
- Each detail is announced with the wording the application itself displays, falling back to the add-on's own label only when none can be recognised. The add-on's label is translated only where the add-on is, so preferring it would have announced English wording in front of a window in another language.

Improvements
- Control+Shift+F9 reports, for each widget in the right column, the state read from the control and the actions it exposes. That is what tells whether the Kill Switch can report its state without opening its settings.

Version 1.8.0

Changed
- Control+Shift+K now switches the Kill Switch instead of stopping at its settings. The widget in the right column is not a switch: activating it opens the settings page, and the shortcut stopped there without even placing the cursor on the switch. The switch itself is a separate control, and the two never exist at the same time: on the main page only the widget exists, and once the page is open only the switch does. The shortcut now switches it where it is, or opens the page and switches it there, places the cursor on it, and announces the state read back from it. If the page opens without the switch appearing, nothing is changed and the add-on says so.

Fixes
- The location you are connected to is back in the list. Once connected, its identifier changes from "Connect to" to "Disconnect from", and the add-on only knew the first form, so the one place you might want to leave had disappeared from Control+Shift+O. It is now listed, announced as connected, and activating it is announced as a disconnection, which is what it does.
- The current traffic no longer reads out the graph. The graph exposes its axis ticks as text, so the announcement ran "13 KB/s, 7.4 KB/s, 600, 300, 0". Only measured values are kept, two at most.
- The protocol is announced with its name: "Protocol: WireGuard (UDP)" rather than "WireGuard (UDP)" alone. It is left out of the traffic shortcut, as the VPN address already was.
- The chevron that expands a country into its cities is announced as Expand, not as a word taken from its identifier.

Improvements
- Control+Shift+F9 also probes the protocol control, so a future change to it shows up in a diagnostic.

Version 1.7.0

Fixes
- The Kill Switch says whether it is on or off wherever that can be read from the control itself, through the Windows accessibility API: on its own settings page, and in what Control+Shift+K reads back after switching it. The four widgets in the right column expose an action and nothing else - no state, and no text saying one - so there they are announced by name alone. Inventing an on or off for a protection from its position in the column is the one thing the add-on will not do. The same applies to NetShield, split tunnelling and port forwarding.
- The state announced after toggling comes from that same source, so it reports the setting as it really is rather than as the screen happens to word it.

New features
- Server load is announced. The connected client exposes it on a control the add-on did not know about.
- Control+Shift+T reads the whole connection details panel instead of two identifiers chosen in advance, so it reports what the panel holds, known to the add-on or not. The VPN address is left out of it: it is a connection detail, not traffic.

Improvements
- Control+Shift+F9 also probes the server load control and the Kill Switch switch, so a future change to either shows up in a diagnostic.

Version 1.6.1

Fixes found by an independent security review of 1.6.0
- The last entry in the countries and cities list could take its name from the connection panel that follows the list, because nothing bounded where its text was looked for. It could therefore be labelled with your real IP address or your account address, in the list and in the log. Each entry's name is now looked for within a bounded window, and the last entry reads its own content only.
- The diagnostic log masks the names of list entries, like every other value it records.
- Choosing an entry in the list now checks that it still points at the same place before connecting. The list stays open while ProtonVPN may rebuild it, so the add-on could have connected to a country other than the one it announced, without saying anything. It now asks you to open the list again.
- The state announced after toggling the Kill Switch is read back from the exact control that was toggled, not from a control matched by wording. A wrong reading here would have claimed a security feature was on when it was not.
- The fallback that finds the connection button by wording no longer searches the control's internal identifier. Every button on the connection card has an identifier containing "Connect", so the change server button could pass for the connect button.

Version 1.6.0

Removed
- The Control+Shift+C shortcut is gone. It claimed to open a country selector but activated whichever unnamed button came second inside the connection card, chosen by position — an information button, not a selector — and then announced "Country selector" whatever happened. Its fallback control was absent from every measurement taken on ProtonVPN 5.1. Use Control+Shift+L for the ProtonVPN search field, or Control+Shift+O for the list of countries and cities.

Fixes
- The NVDA log no longer records anything that identifies you. The account address shown by the Account button was written to it in full, and the log is what gets attached to a bug report. Account addresses and the Windows account name in file paths are now masked, as IP addresses already were.
- The Kill Switch shortcut no longer falls back to the widget's position in the column. That fallback could toggle a different security feature than the one asked for, silently, because activation tries the toggle action right after the invoke action. The Kill Switch is identified by its exact identifier, found in every measurement; when it cannot be identified, the add-on says so and changes nothing.
- The last-resort activation no longer presses Enter without checking that the focus reached the intended control. A refused focus change used to let that keypress land on whatever held the focus before.

Version 1.5.0

Fixes
- A drop-down list no longer reads out an internal class name as its value. The default connection list announced "ProtonVPN.Client.UI.Main.Settings.Pages.ConnectionPreferences.DefaultConnectionItem"; it now announces what is actually selected, such as "Fastest country".
- The default connection list, the banner and the controls around them are announced with a proper name instead of one spelled out from their identifier in English.

Improvements
- When a selection cannot be read, nothing is announced as the value rather than an internal name: a list without a spoken value is easier to live with than a class name read out loud.

Version 1.4.0

Fixes
- Check boxes and radio buttons in the settings are announced by name. ProtonVPN leaves them without one, and the add-on only looked at buttons, so the NAT type, the OpenVPN driver and the local network options were announced as nothing but their role.
- Buttons that carry an identifier but no name are announced too. Close settings, Back, Account, the default connection selector and the banner buttons were all silent.
- What a setting explains below its title is read with NVDA+Tab instead of being lost.
- In the default connection list, an entry made of two parts is announced in full: "United States, Massachusetts" rather than "United States".

New features
- Control+Shift+F10 now names roles, states and control types instead of printing their numbers, so a report can be read without a lookup table.

Improvements
- A control the add-on cannot name is left to NVDA, which announces its role, rather than being given an invented label. Where the identifier says enough, it is turned into words.

Version 1.3.0

Fixes
- Cities are now attached to the right country. ProtonVPN lists a country's cities before the country itself, so each city was being announced under the country just above it in the alphabet: Phnom Penh under Bulgaria instead of Cambodia.
- Countries and cities are announced in the order the screen shows them: each country, then its own cities.
- Internal names ProtonVPN exposes for its own use are no longer spoken. A country row used to end with "ExpanderButtonContent".
- In the connection preferences, the five choices of the default connection list all announced the same thing. Each one is now announced by what it actually shows.

New features
- Control+Shift+F10 describes the focused control in the NVDA log and copies the description to the clipboard: identifier, type, name as the application gives it, name as the add-on announces it, states, contents and available actions. That is what a badly labelled control needs for a report.

Improvements
- Countries and cities are told apart by their identifier rather than by their position on screen. The position was not readable in every case, and an unreadable position was being taken for the top of the list.

Version 1.2.0

Fixes
- NVDA no longer crashes when you open the cities of a country. Reading a city made the add-on read the country row around it, which made it read the city again, with no end to it.
- Countries and cities are announced in the order they appear on screen. Cities used to turn up in the middle of the country list, as if they were countries.
- Buttons that already carry a name of their own are no longer relabelled.

New features
- The cities are covered. Control+Shift+O opens a searchable list of every country and city on display, and each city is announced with the country it belongs to.
- A country that holds cities says how many.
- What a row shows besides its name, such as the number of servers, is read with NVDA+Tab.

Improvements
- Tested with NVDA 2026.3.
- The add-on reads the ProtonVPN window in one go instead of element by element: shortcuts answer much faster, and moving through the country list no longer makes NVDA lag.
- Control+Shift+L still takes you to the ProtonVPN search field.

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
