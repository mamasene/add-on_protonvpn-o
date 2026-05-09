# -*- coding: utf-8 -*-
"""
Configuration de build pour l'add-on NVDA ProtonVPN Accessibility.
Ce fichier est utilisé par SCons pour générer le package .nvda-addon.
"""

# Informations de l'add-on
addon_info = {
    "addon_name": "protonVPNAccessibility",
    "addon_summary": "Amélioration de l'accessibilité de ProtonVPN",
    "addon_description": """Améliore l'accessibilité de l'application ProtonVPN pour Windows avec NVDA.

Fonctionnalités principales :
- Labellisation des boutons et contrôles (Connecter, Déconnecter, widgets)
- Annonces dynamiques : Label + Valeur (IP, pays, fournisseur, trafic)
- Raccourcis clavier pour actions rapides (Ctrl+Shift+D/K/C/T)
- Support VPN connecté : IP VPN, trafic total, trafic en temps réel

Projet communautaire non affilié à Proton AG.""",
    "addon_version": "1.0.0",
    "addon_changelog": """Version 1.0.0 :
- Labellisation complète des contrôles ProtonVPN
- Extraction dynamique des valeurs (IP, pays, fournisseur, trafic)
- Raccourcis : Ctrl+Shift+D (VPN), K (Kill Switch), C (Pays), T (Trafic)
- Documentation HTML embarquée (FR/EN)""",
    "addon_author": "Mama Sene <tech.access33@gmail.com>",
    "addon_url": "https://github.com/mamasene/add-on_protonvpn",
    "addon_sourceURL": "https://github.com/mamasene/add-on_protonvpn",
    "addon_docFileName": "readme.html",
    "addon_minimumNVDAVersion": "2025.1",
    "addon_lastTestedNVDAVersion": "2026.1",
    "addon_updateChannel": None,
    "addon_license": "GPL v2",
    "addon_licenseURL": "https://www.gnu.org/licenses/gpl-2.0.html",
}


# Fichiers source Python à inclure
pythonSources = [
    "addon/appModules/*.py",
]

# Fichiers à traduire
i18nSources = pythonSources + ["buildVars.py"]

# Fichiers à exclure du package
excludedFiles = [
    "*.pyc",
    "__pycache__",
    "*.pyo",
]

# Langue de base (pour la documentation)
baseLanguage = "en"

# Extensions markdown pour la documentation
markdownExtensions = []

# Tables braille personnalisées (vide pour cet add-on)
brailleTables = {}

# Dictionnaires de symboles (vide pour cet add-on)
symbolDictionaries = {}
