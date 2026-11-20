# -*- coding: utf-8 -*-
"""
Configuration de build pour l'add-on NVDA ProtonVPN Accessibility.
Ce fichier est utilisé par SCons pour générer le package .nvda-addon.
"""

# Informations de l'add-on
addon_info = {
    "addon_name": "protonVPNAccessibility",
    "addon_summary": "ProtonVPN Accessibility",
    "addon_description": """Improves accessibility of the ProtonVPN Windows application for NVDA users.

Main features:
- Proper labeling of buttons and controls
- A searchable list of every country and city on display
- Dynamic announcements for VPN status information
- Announcements for IP address, country, provider and traffic
- Keyboard shortcuts for quick actions
- French and English documentation

This is a community add-on and is not affiliated with Proton AG.""",
    "addon_version": "2.0.0",
    "addon_changelog": """Version 2.0.0:

ProtonVPN can now be used from end to end with NVDA: the cities are covered, every control says what it is, and the Kill Switch really switches.

New features:
- The cities are there. Control+Shift+O opens a searchable list of every country and city on display, and each city is announced with the country it belongs to.
- Control+Shift+L takes you to the ProtonVPN search field, to reach a country in a few letters.
- Control+Shift+K turns the Kill Switch on and off, then tells you the state it reads back from it. In the right-hand column it announces its name alone: ProtonVPN does not publish its state there.
- Control+Shift+T announces the connection: traffic, server load, VPN address and protocol.
- Control+Shift+D connects and disconnects, and says so only once it has really happened.
- Two shortcuts help with a bug report: Control+Shift+F9 writes a diagnostic to the NVDA log, and Control+Shift+F10 describes the control you are on.

Fixes:
- NVDA no longer crashes when you open the cities of a country.
- Each city is announced under its own country, and the list follows the order on screen.
- The country you are connected to is in the list, and says that it is connected.
- Buttons, check boxes and radio buttons that announced nothing now have a name, in the main window as well as in the settings.
- Internal names are no longer read out loud, neither as a name nor as the value of a drop-down list.
- The add-on speaks French.
- Your IP address and your account address no longer reach the NVDA log, which is the file you attach to a bug report.
- A shortcut that pressed the wrong button has been removed, and the Kill Switch can no longer be mistaken for another protection.

Improvements:
- Moving through the interface answers straight away. Going down the country list no longer makes NVDA lag, and the shortcuts answer without waiting.
- Tested with NVDA 2026.3.

Version 1.0.1:
- Updated add-on display name for international users
- Fixed project repository URL
- Improved manifest metadata
- Updated French translation metadata

Version 1.0.0:
- Initial stable release
- Improved ProtonVPN interface accessibility
- Added keyboard shortcuts
- Added dynamic announcements for VPN status
- Added French and English documentation""",
    "addon_author": "Mama Sene <tech.access33@gmail.com>",
    "addon_url": "https://github.com/mamasene/add-on_protonvpn-o",
    "addon_sourceURL": "https://github.com/mamasene/add-on_protonvpn-o",
    "addon_docFileName": "readme.html",
    "addon_minimumNVDAVersion": "2025.1",
    "addon_lastTestedNVDAVersion": "2026.3",
    "addon_updateChannel": "stable",
    "addon_license": "GPL v2",
    "addon_licenseURL": "https://www.gnu.org/licenses/gpl-2.0.html",
}


# Fichiers source Python à inclure
pythonSources = [
    "addon/appModules/*.py",
]

# Fichiers à traduire
i18nSources = pythonSources + ["buildVars.py"]

# Fichiers à exclure du package (motifs appliqués à chaque composant du chemin).
# Seule déclaration : tools/package.py les lit, aucun script de build ne les recopie.
excludedFiles = [
    "*.pyc",
    "__pycache__",
    "*.pyo",
    "*.po",  # seul le .mo compilé est utile à l'exécution
]

# Langue de base (pour la documentation)
baseLanguage = "en"

# Extensions markdown pour la documentation
markdownExtensions = []

# Tables braille personnalisées (vide pour cet add-on)
brailleTables = {}

# Dictionnaires de symboles (vide pour cet add-on)
symbolDictionaries = {}