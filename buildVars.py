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
- Dynamic announcements for VPN status information
- Announcements for IP address, country, provider and traffic
- Keyboard shortcuts for quick actions
- French and English documentation

This is a community add-on and is not affiliated with Proton AG.""",
    "addon_version": "1.1.0",
    "addon_changelog": """Version 1.1.0:

New features:
- Search for a country with Control+Shift+L: the add-on takes you straight to the ProtonVPN search field, so you can reach any country by typing a few letters
- The country list is now readable: each country is announced by its name instead of an internal code
- NetShield, Kill Switch, Split tunneling and Port forwarding are announced by name, together with whether each one is on or off

Fixes:
- The add-on now speaks French. The translation was not being applied at all
- The Kill Switch, traffic and country shortcuts work again, including while the VPN is connected
- The country shortcut now works while connected, by opening the server change panel
- The connection status is announced only once the change has actually happened, and the add-on now tells you when nothing changed

Improvements:
- Keyboard shortcuts respond much faster
- NVDA no longer risks freezing while ProtonVPN is establishing a connection
- IP addresses are no longer written to the NVDA log, which is often attached to bug reports
- Add-on summary, description and version history are now available in French
- The license file now ships with the add-on

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
    "addon_lastTestedNVDAVersion": "2026.1",
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