"""
Add-on NVDA - Module d'application ProtonVPN
Fichier: protonvpnservice.py

La version fait foi dans buildVars.py uniquement : ne pas la recopier ici.

Améliore l'accessibilité de ProtonVPN avec :
- Lecture de l'arbre UIA en un seul appel inter-processus (pas d'OCR)
- Liste des pays ET des villes, avec leur hiérarchie réelle
- Libellés et états lus dans ce que l'application affiche

RÈGLE D'OR DE CE MODULE
-----------------------
Rien, ici, ne doit lire ``obj.name`` ni parcourir ``obj.children`` sur un
NVDAObject pour construire un libellé.

Lire ``obj.name`` appelle ``_get_name`` des classes overlay ci-dessous ;
parcourir ``obj.children`` fabrique un NVDAObject par nœud, donc rappelle
``chooseNVDAObjectOverlayClasses``, donc ``_get_name``, donc le parcours…
Dans la liste des villes, où des boutons sans nom sont imbriqués dans d'autres
boutons sans nom, cette boucle n'a pas de fond : elle faisait planter NVDA.

Tout passe donc par les éléments UIA bruts (``element_*`` plus bas), lus par
lots avec le cache d'UIA : aucun NVDAObject n'est construit, et un sous-arbre
entier coûte un seul aller-retour au lieu d'un par nœud.

RACCOURCIS (dans ProtonVPN uniquement):
- Ctrl+Shift+D : Connecter / Déconnecter le VPN
- Ctrl+Shift+K : Activer / Désactiver le Kill Switch
- Ctrl+Shift+T : Annoncer les informations de trafic
- Ctrl+Shift+L : Rechercher un pays dans le champ de ProtonVPN
- Ctrl+Shift+O : Ouvrir la liste des pays et des villes de l'add-on
- Ctrl+Shift+F9 : Écrire un diagnostic dans le journal de NVDA
- Ctrl+Shift+F10 : Décrire le contrôle actif (journal + presse-papiers)
"""

# ============================================================================
# LOG IMMEDIAT AU CHARGEMENT
# ============================================================================
from logHandler import log
log.info("PROTONVPN: protonvpnservice.py loading...")

# ============================================================================
# IMPORTS
# ============================================================================
import collections
import re
import threading
import time
import unicodedata

import api
import appModuleHandler
import controlTypes
import ui
from NVDAObjects.UIA import UIA
from scriptHandler import script

try:
    import wx
    import gui
    GUI_AVAILABLE = True
except Exception as e:  # pragma: no cover - dépend de l'environnement NVDA
    log.error(f"PROTONVPN: wx/gui unavailable: {e}")
    GUI_AVAILABLE = False

try:
    import addonHandler
    addonHandler.initTranslation()
except Exception as e:
    log.error(f"PROTONVPN: addonHandler error: {e}")
    _ = lambda x: x  # noqa: E731

# initTranslation installe aussi ngettext ; absent, on retombe sur une forme
# simple plutôt que de laisser une NameError casser le chargement du module.
try:
    _plural = ngettext  # noqa: F821 - injecté par addonHandler.initTranslation
except NameError:
    def _plural(singular, plural, count):
        return singular if count == 1 else plural


# ============================================================================
# CONFIGURATION
# ============================================================================
DEBUG_MODE = False

# Données personnelles à masquer avant toute écriture dans le journal.
IP_REGEX = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b')
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
# Le groupe capturé garde « C:\Users\ » et ne masque que le nom du compte, ce
# qui laisse le chemin lisible pour le diagnostic.
USER_PATH_REGEX = re.compile(
    r'([A-Za-z]:[\\/]Users[\\/])[^\\/\s"\']+', re.IGNORECASE
)

# Libellés permettant d'identifier le widget Kill Switch, quelle que soit sa
# position dans la colonne (l'ordre varie selon l'offre et la version de l'app).
KILL_SWITCH_KEYWORDS = (
    "kill switch", "killswitch", "arrêt d'urgence", "coupe-circuit",
    "coupure d'urgence", "interrupteur d'arrêt",
)

# AutomationId réels des widgets de la colonne droite, relevés dans l'arbre UIA
# de ProtonVPN. Il n'existe pas d'identifiant générique « WidgetButton » :
# chaque widget porte le sien.
WIDGET_AUTOMATION_IDS = {
    "NetShieldWidgetButton": _("NetShield"),
    "KillSwitchWidgetButton": _("Kill Switch"),
    "SplitTunnelingWidgetButton": _("Split tunneling"),
    "PortForwardingWidgetButton": _("Port forwarding"),
}

KILL_SWITCH_AUTOMATION_ID = "KillSwitchWidgetButton"

# L'interrupteur lui-même, dans la page de réglage de l'arrêt d'urgence. Les
# relevés montrent que les deux ne coexistent pas : sur la page principale, seul
# le widget existe ; la page de réglage ouverte, seul l'interrupteur existe.
# D'où l'enchaînement du raccourci : basculer l'interrupteur s'il est là, sinon
# ouvrir la page par le widget puis basculer.
KILL_SWITCH_TOGGLE_AUTOMATION_ID = "KillSwitchToggle"

# Délai laissé à la page de réglage pour s'afficher avant d'y chercher
# l'interrupteur.
SETTINGS_PAGE_DELAY_MS = 700

# Autres boutons à AutomationId connu, que ProtonVPN n'étiquette pas toujours.
SIDE_BUTTON_LABELS = {
    "SettingsButton": _("Settings"),
    "TitleBarMenuButton": _("Main menu"),
}

# Contrôles que ProtonVPN laisse sans nom et dont le contenu ne dit pas la
# fonction. Le bouton Compte, par exemple, contient l'adresse du compte et
# l'offre souscrite : utile en description, trompeur comme nom.
#
# N'y figurent que des identifiants dont le sens ne prête pas à interprétation.
# Pour les autres, l'AutomationId mis en mots reste plus honnête qu'un libellé
# supposé : une étiquette fausse inspire confiance, une étiquette approximative
# invite à vérifier.
# Le bouton qui ferme les paramètres : il n'existe que lorsqu'ils sont ouverts,
# ce qui en fait un repère fiable de l'écran affiché.
CLOSE_SETTINGS_AUTOMATION_ID = "CloseSettingsButton"

AUTOMATION_ID_LABELS = {
    CLOSE_SETTINGS_AUTOMATION_ID: _("Close settings"),
    "GoBackButton": _("Back"),
    "AccountButton": _("Account"),
    "BannerDismissButton": _("Dismiss banner"),
    "BannerImageActionButton": _("Banner"),
    "DefaultConnectionSelectorButton": _("Choose the default connection"),
    "DefaultConnectionDropdown": _("Default connection"),
    # Le chevron qui déplie un pays pour montrer ses villes. Sans nom ni
    # contenu, il s'annonçait « Expander », tiré de son identifiant.
    "ExpanderButton": _("Expand"),
}

# Identifiants dont le libellé retenu vaut dans n'importe quelle page. Pour
# ceux-là, savoir dans quel conteneur se trouve le bouton ne change rien à
# l'annonce : la remontée d'ancêtres ne serait que cinq allers-retours vers
# l'application payés pour rien, à chaque passage du focus.
#
# « BannerImageActionButton » n'y figure pas : dans une carte promotionnelle,
# c'est le texte de l'offre qui le désigne le mieux — « Passer à VPN Plus »
# plutôt que « Bannière » —, et ce texte, seul son conteneur le fait lire.
PAGE_INDEPENDENT_LABEL_IDS = frozenset((
    CLOSE_SETTINGS_AUTOMATION_ID,
    "GoBackButton",
    "AccountButton",
    "BannerDismissButton",
    "DefaultConnectionSelectorButton",
    "DefaultConnectionDropdown",
    "ExpanderButton",
))

# Suffixes techniques retirés avant de mettre un AutomationId en mots.
AUTOMATION_ID_SUFFIXES = (
    "RadioButton", "ToggleButton", "ToggleSwitch", "CheckBox", "ComboBox",
    "TextBox", "Button", "Item", "Control",
)

# ProtonVPN expose un bouton par emplacement, dont l'AutomationId est préfixé
# (Connect_to_DE, Connect_to_SN, Connect_to_Fastest…) et dont le contenu porte
# le nom du pays ou de la ville dans la langue de l'interface.
COUNTRY_BUTTON_PREFIX = "Connect_to_"

# Une fois le VPN connecté, la ligne active change d'identifiant :
# « Connect_to_Fastest » devient « Disconnect_from_Fastest ». L'add-on ne
# connaissait que le premier, si bien que l'emplacement en cours d'utilisation
# disparaissait de sa liste — le seul, pourtant, que l'utilisateur peut vouloir
# quitter.
DISCONNECT_LOCATION_PREFIX = "Disconnect_from_"

LOCATION_BUTTON_PREFIXES = (COUNTRY_BUTTON_PREFIX, DISCONNECT_LOCATION_PREFIX)

# Une ligne de pays porte le code ISO à deux lettres : Connect_to_DE,
# Connect_to_KH. Une ligne de ville ou de région porte son nom en clair :
# Connect_to_Montréal, Connect_to_Phnom Penh, Connect_to_Texas. Le journal de
# diagnostic de ProtonVPN 5.1 le montre sans ambiguïté, et c'est le seul signal
# fiable : les rectangles des éléments, eux, reviennent à zéro dès que la
# propriété n'est pas dans le cache, ce qui rendait tout raisonnement sur
# l'indentation faux sans prévenir.
COUNTRY_CODE_RE = re.compile(r'^[A-Za-z]{2}$')
FASTEST_ID_FRAGMENT = "fastest"

# Champ de recherche de ProtonVPN. Il filtre la liste complète des pays, y
# compris ceux que l'interface n'a pas encore matérialisés.
SEARCH_BOX_AUTOMATION_ID = "SearchTextBox"

# Certains éléments — les onglets de la liste des pays notamment — sont nommés
# par ProtonVPN avec le nom complet de leur classe interne, du type
# « ProtonVPN.Client.UI.Main.….P2PCountriesComponentViewModel ».
QUALIFIED_NAME_PREFIX = "ProtonVPN."

CLASS_NAME_SUFFIXES = ("ComponentViewModel", "ViewModel", "Component")

INTERNAL_NAME_LABELS = {
    "AllCountries": _("All countries"),
    "SecureCoreCountries": _("Secure Core"),
    "P2PCountries": _("P2P"),
    "TorCountries": _("Tor"),
    "DefaultConnectionItem": _("Default connection"),
    "RecentDefaultConnectionItem": _("Recent connection"),
}

# Noms de pièces de gabarit XAML : « ExpanderButtonContent »,
# « SecondaryButtonContent »… ProtonVPN les expose comme noms d'éléments, et ils
# se retrouvaient lus à voix haute au bout d'une ligne de pays. Ce ne sont pas
# des libellés : c'est de la plomberie d'interface.
TEMPLATE_PART_SUFFIXES = ("ButtonContent", "Presenter", "ContentControl")

# Conteneurs reconnus, cherchés par un unique remontée d'ancêtres.
CONTAINER_LOCATION_DETAILS = "LocationDetailsPage"
CONTAINER_CONNECTION_DETAILS = "ConnectionDetailsPage"
CONTAINER_OVERLAY = "OverlayMessage"
CONTAINER_CONNECTION_CARD = "ConnectionCard"

KNOWN_CONTAINER_IDS = frozenset((
    CONTAINER_LOCATION_DETAILS,
    CONTAINER_CONNECTION_DETAILS,
    CONTAINER_OVERLAY,
))

# Quand le VPN est connecté, LocationDetailsPage n'existe pas : le changement de
# serveur passe par ce bouton de la carte de connexion.
CHANGE_SERVER_AUTOMATION_ID = "ConnectionCardChangeServerButton"

# Textes d'état affichés par les widgets, comparés en égalité stricte :
# une recherche par sous-chaîne ferait correspondre "on" à n'importe quel mot.
WIDGET_STATE_ON = frozenset((
    "on", "actif", "active", "activé", "activée", "enabled", "activated",
))
WIDGET_STATE_OFF = frozenset((
    "off", "inactif", "inactive", "désactivé", "désactivée", "disabled", "deactivated",
))

# Widgets de la colonne droite, identifiés par le texte qu'ils affichent.
# L'ordre de la colonne varie selon l'offre et la version de ProtonVPN :
# l'identité d'un widget ne doit jamais être déduite de sa position.
WIDGET_DEFINITIONS = (
    (("netshield", "net shield"), _("NetShield")),
    (KILL_SWITCH_KEYWORDS, _("Kill Switch")),
    (("split tunneling", "tunnel divisé", "tunnelage divisé"), _("Split tunneling")),
    (("port forwarding", "redirection de port"), _("Port forwarding")),
)

# Repli pour le bouton principal quand les AutomationId attendus sont absents.
DISCONNECT_KEYWORDS = ("disconnect", "déconnecter")
CONNECT_KEYWORDS = ("connect", "connecter")

# Second repli, hors carte de connexion : le libellé complet doit correspondre.
DISCONNECT_LABELS = frozenset(("disconnect", "déconnecter", "se déconnecter"))
CONNECT_LABELS = frozenset(("connect", "connecter", "se connecter"))

# Confirmation d'état après action : une connexion ProtonVPN dépasse souvent
# une seconde et demie, il faut donc sonder plusieurs fois.
VPN_STATE_POLL_MS = 1200
VPN_STATE_MAX_ATTEMPTS = 8

# Délai avant relecture de l'état d'un widget basculé.
WIDGET_STATE_POLL_MS = 800

# ============================================================================
# GARDE-FOUS
# ============================================================================
# Aucune lecture de l'arbre ne doit pouvoir durer indéfiniment : NVDA n'a qu'un
# seul thread pour la parole, le braille et les événements. Tout passe donc par
# des appels groupés, dont le résultat est plafonné en nombre d'éléments, et par
# des remontées bornées en niveaux : plus aucun parcours récursif, dont la
# profondeur ne disait rien de la largeur de l'arbre — et la liste des serveurs
# de ProtonVPN est très large.

# Plafond d'éléments rapportés pour un sous-arbre (le libellé d'une ligne).
SUBTREE_MAX_ELEMENTS = 80

# Plafond d'éléments rapportés pour la fenêtre entière.
MAX_SNAPSHOT_ELEMENTS = 4000

# Plafond de lignes d'emplacement présentées dans le dialogue.
MAX_LOCATION_ROWS = 600

# Plafond de boutons détaillés par le diagnostic. Au-delà, on lit la liste des
# pays, qui n'apprend plus rien sur la structure de l'interface.
MAX_DIAGNOSTIC_BUTTONS = 20

# Nombre d'éléments, après une ligne, où chercher son libellé. Les relevés sur
# ProtonVPN 5.1 en montrent trois à cinq ; cette marge les couvre largement tout
# en empêchant une ligne d'adopter le texte du panneau qui suit la liste.
ROW_TEXT_WINDOW = 12

# Remontée d'ancêtres : cinq niveaux suffisent pour atteindre le conteneur d'un
# bouton, et bornent le coût quoi qu'il arrive.
MAX_ANCESTOR_LEVELS = 5

# Types de contrôle UIA utilisés dans ce module.
UIA_EDIT_CONTROL_TYPE = 50004
UIA_BUTTON_CONTROL_TYPE = 50000

# Motif UIA donnant l'élément retenu dans une liste (UIA_SelectionPatternId).
UIA_SELECTION_PATTERN_ID = 10001

# Motif UIA donnant l'état d'un interrupteur (UIA_TogglePatternId), et les
# valeurs de ToggleState : 0 éteint, 1 allumé, 2 indéterminé.
UIA_TOGGLE_PATTERN_ID = 10015
TOGGLE_STATE_OFF = 0
TOGGLE_STATE_ON = 1

# Un élément de liste, d'onglet ou d'arbre porte son propre libellé dans son
# contenu, à la différence du conteneur qui l'héberge.
# Identifiants officiels de l'API UIA (UIA_*ControlTypeId).
ITEM_CONTROL_TYPES = frozenset((
    50007,  # ListItem
    50011,  # MenuItem
    50013,  # RadioButton
    50019,  # TabItem
    50024,  # TreeItem
    50029,  # DataItem
))

# Contrôles sur lesquels l'utilisateur se déplace et agit. Un contrôle de cette
# liste laissé sans nom par ProtonVPN est repris par l'add-on.
#
# La liste est volontairement fermée : l'étendre aux conteneurs ferait examiner
# chaque panneau et chaque groupe de la fenêtre, pour des éléments que personne
# n'atteint au clavier.
INTERACTIVE_CONTROL_TYPES = frozenset((
    50000,  # Button
    50002,  # CheckBox
    50003,  # ComboBox
    50004,  # Edit
    50005,  # Hyperlink
    50007,  # ListItem
    50011,  # MenuItem
    50013,  # RadioButton
    50015,  # Slider
    50019,  # TabItem
    50024,  # TreeItem
    50029,  # DataItem
    50031,  # SplitButton
))

# Contrôles qui portent une sélection. Leur valeur, telle que l'API UIA la rend,
# est le nom de l'élément retenu — donc le nom de sa classe interne chez
# ProtonVPN. Ils sont repris qu'ils soient nommés ou non.
SELECTION_CONTROL_TYPES = frozenset((
    50003,  # ComboBox
    50008,  # List
    50018,  # Tab
    50023,  # Tree
))

# Noms des types de contrôle, pour que le diagnostic se lise.
CONTROL_TYPE_NAMES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
    50023: "Tree", 50024: "TreeItem", 50025: "Custom", 50026: "Group",
    50027: "Thumb", 50028: "DataGrid", 50029: "DataItem", 50030: "Document",
    50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
    50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator",
}

_local = threading.local()


class labelling:
    """Interdit toute ré-entrée dans le calcul d'un libellé, par thread.

    ``with labelling() as first:`` donne False si un libellé est déjà en cours
    de calcul plus bas dans la pile. Les classes overlay s'en servent pour
    rendre immédiatement le nom brut de l'application : c'est le filet qui
    garantit qu'aucune combinaison de nœuds imbriqués ne peut reboucler.
    """

    __slots__ = ("first",)

    def __enter__(self):
        depth = getattr(_local, "labelling", 0)
        _local.labelling = depth + 1
        self.first = depth == 0
        return self.first

    def __exit__(self, *exc_info):
        _local.labelling = max(0, getattr(_local, "labelling", 1) - 1)
        return False


def get_addon_version():
    """Retourne la version déclarée dans le manifeste de l'add-on.

    Le manifeste est généré depuis buildVars.py : c'est la seule source de vérité.
    """
    try:
        return addonHandler.getCodeAddon().manifest["version"]
    except Exception:
        return "unknown"


def redact(text):
    """Masque les données personnelles avant journalisation.

    Le journal de NVDA est fréquemment joint tel quel à un rapport de bug
    public : rien de ce qui identifie l'utilisateur ne doit y figurer.

    Trois familles, toutes rencontrées dans l'interface de ProtonVPN :
    l'adresse IP réelle et celle du tunnel ; l'adresse du compte, qu'affiche le
    bouton Compte des paramètres ; le nom du compte Windows, que les chemins du
    tunnel divisé font apparaître.
    """
    if not text:
        return text

    masked = str(text)
    masked = IP_REGEX.sub("[ip]", masked)
    masked = EMAIL_REGEX.sub("[email]", masked)
    masked = USER_PATH_REGEX.sub(r"\1[user]", masked)
    return masked


# ============================================================================
# ACCÈS BAS NIVEAU AUX ÉLÉMENTS UIA
# ============================================================================

def _uia_attr(obj, *names):
    """Retourne le premier attribut existant parmi names.

    comtypes expose les membres COM tantôt en PascalCase, tantôt avec une
    initiale minuscule selon la génération du typelib : on accepte les deux
    plutôt que de parier sur une seule orthographe.
    """
    for name in names:
        try:
            value = getattr(obj, name, None)
        except Exception:
            continue
        if value is not None:
            return value
    return None


def _read(element, *names):
    """Première propriété lisible parmi names, cache d'abord.

    Une propriété absente du cache lève une COMError : on passe alors à la
    variante « Current », au prix d'un aller-retour.
    """
    if element is None:
        return None
    for name in names:
        try:
            value = getattr(element, name)
        except Exception:
            continue
        if value is not None:
            return value
    return None


def element_name(element):
    return _read(
        element, 'CachedName', 'cachedName', 'CurrentName', 'currentName'
    ) or ""


def element_automation_id(element):
    return _read(
        element, 'CachedAutomationId', 'cachedAutomationId',
        'CurrentAutomationId', 'currentAutomationId',
    ) or ""


def element_current_automation_id(element):
    """AutomationId relu dans l'application, en ignorant le cache.

    Sert à vérifier qu'un élément saisi plus tôt désigne toujours la même chose.
    La variante en cache répondrait la valeur d'alors, ce qui validerait
    n'importe quel élément recyclé.
    """
    return _read(element, 'CurrentAutomationId', 'currentAutomationId') or ""


def element_control_type(element):
    return _read(
        element, 'CachedControlType', 'cachedControlType',
        'CurrentControlType', 'currentControlType',
    ) or 0


def element_framework_id(element):
    return _read(
        element, 'CachedFrameworkId', 'cachedFrameworkId',
        'CurrentFrameworkId', 'currentFrameworkId',
    ) or ""


def _rect_tuple(rect):
    """(gauche, haut, droite, bas) si le rectangle a une surface, sinon None.

    Un rectangle nul est rejeté : selon les éléments, une propriété absente du
    cache lève une erreur ou rend une structure à zéro, et un zéro pris pour une
    coordonnée réelle fausse tout raisonnement sur les positions.
    """
    if rect is None:
        return None
    try:
        box = (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def element_cached_rect(element):
    """Rectangle lu dans le cache uniquement, ou None.

    Sans repli sur la propriété courante : utilisé là où des centaines
    d'éléments sont parcourus, un aller-retour par élément n'est pas acceptable.
    """
    return _rect_tuple(
        _read(element, 'CachedBoundingRectangle', 'cachedBoundingRectangle')
    )


def element_rect(element):
    """Rectangle (gauche, haut, droite, bas) de l'élément, ou None.

    Interroge l'application si le cache ne donne rien d'exploitable : réservé
    aux usages ponctuels, pas aux parcours.
    """
    return element_cached_rect(element) or _rect_tuple(
        _read(element, 'CurrentBoundingRectangle', 'currentBoundingRectangle')
    )


def _enum_name(value):
    """Nom d'un membre d'énumération, sa valeur à défaut.

    Les énumérations de NVDA dérivent de IntEnum : depuis Python 3.11, str()
    rend le nombre, inutilisable dans un rapport de diagnostic.
    """
    return getattr(value, 'name', None) or str(value)


def _element_of(obj):
    """Élément UIA d'un NVDAObject, ou None."""
    try:
        return getattr(obj, 'UIAElement', None)
    except Exception:
        return None


def get_automation_id(obj):
    """AutomationId d'un NVDAObject, sans déclencher de classe overlay."""
    try:
        value = getattr(obj, 'UIAAutomationId', None)
    except Exception:
        value = None
    if value:
        return value
    return element_automation_id(_element_of(obj))


def raw_name(obj):
    """Nom exposé par l'application, sans passer par les classes overlay.

    Lire ``obj.name`` appellerait ``_get_name`` : c'est précisément la boucle
    qui faisait planter NVDA dans la liste des villes.
    """
    return element_name(_element_of(obj))


def get_framework_id(obj):
    try:
        value = getattr(obj, 'UIAFrameworkId', None)
    except Exception:
        value = None
    if value:
        return value
    return element_framework_id(_element_of(obj))


def get_bounding_rect(obj):
    """Rectangle d'un NVDAObject, lu sur l'élément UIA puis sur la location."""
    rect = element_rect(_element_of(obj))
    if rect:
        return rect
    try:
        loc = obj.location
        if loc:
            return (loc.left, loc.top, loc.left + loc.width, loc.top + loc.height)
    except Exception:
        pass
    return None


# ============================================================================
# CLIENT UIA, CONDITIONS ET REQUÊTES DE CACHE
# ============================================================================

def _uia_handler():
    try:
        import UIAHandler
        return UIAHandler
    except Exception as e:
        log.debugWarning(f"PROTONVPN: UIAHandler unavailable: {e}")
        return None


def _client():
    handler = _uia_handler()
    if handler is None:
        return None
    return getattr(handler.handler, 'clientObject', None)


def _property_id(name, default):
    handler = _uia_handler()
    return getattr(handler, name, default) if handler else default


def _tree_scope(name, default):
    handler = _uia_handler()
    return getattr(handler, name, default) if handler else default


def _true_condition():
    client = _client()
    create = _uia_attr(client, 'CreateTrueCondition', 'createTrueCondition') if client else None
    return create() if create else None


# Objets UIA réutilisables, reconstruits si NVDA remplace son client UIA.
# Les refabriquer à chaque libellé coûterait plusieurs appels COM par ligne
# parcourue à la flèche, pour un résultat rigoureusement identique.
_shared_objects = {}


def _shared(key, factory):
    """Objet UIA partagé, lié au client qui l'a produit.

    La clé inclut l'identité du client : si NVDA redémarre son interface UIA,
    l'objet mis de côté devient inutilisable et doit être refait, sans quoi les
    libellés cesseraient silencieusement de se construire.
    """
    client = _client()
    if client is None:
        return None

    cached = _shared_objects.get(key)
    if cached is not None and cached[0] is client:
        return cached[1]

    value = factory()
    if value is None:
        return None

    # Le client est gardé dans l'entrée, et non seulement son identité : sans
    # cette référence, il pourrait être libéré, un autre objet reprendre son
    # adresse, et un objet de cache périmé passer pour valide.
    _shared_objects[key] = (client, value)
    return value


def _build_cache_request(property_ids, from_base=False):
    """Requête de cache sur les propriétés demandées.

    ``from_base`` part de la requête de NVDA : indispensable dès qu'un élément
    rapporté servira à construire un NVDAObject, car NVDAObjects.UIA lit à la
    construction des propriétés mises en cache, et un élément obtenu avec une
    requête plus pauvre fait échouer l'instanciation.
    """
    request = None

    if from_base:
        handler = _uia_handler()
        base = getattr(handler.handler, 'baseCacheRequest', None) if handler else None
        clone = _uia_attr(base, 'Clone', 'clone') if base is not None else None
        if clone is not None:
            try:
                request = clone()
            except Exception as e:
                log.debugWarning(f"PROTONVPN: cannot clone base cache request: {e}")

    if request is None:
        client = _client()
        create = _uia_attr(client, 'CreateCacheRequest', 'createCacheRequest') if client else None
        if create is None:
            return None
        try:
            request = create()
        except Exception as e:
            log.debugWarning(f"PROTONVPN: cannot create cache request: {e}")
            return None

    add = _uia_attr(request, 'AddProperty', 'addProperty')
    if add is None:
        return None

    for property_id in property_ids:
        try:
            add(property_id)
        except Exception:
            # Une propriété refusée n'invalide pas les autres.
            pass

    if not from_base:
        # Portée « élément seul » : mettre les ancêtres en cache pour chacun des
        # centaines d'éléments rapportés multiplierait le volume transféré sans
        # qu'aucun appelant ne les lise. La requête de NVDA, elle, garde la
        # portée qu'elle s'est donnée : les NVDAObjects construits à partir de
        # ces éléments comptent dessus.
        try:
            request.TreeScope = _tree_scope('TreeScope_Element', 1)
        except Exception:
            pass

    return request


def _find_all(root, scope, condition, cache_request):
    """FindAll avec cache. Retourne (liste d'éléments, explication)."""
    if root is None:
        return [], "no root element"
    if condition is None:
        return [], "no UIA condition"

    find_cached = _uia_attr(root, 'FindAllBuildCache', 'findAllBuildCache')
    try:
        if find_cached is not None and cache_request is not None:
            array = find_cached(scope, condition, cache_request)
            reason = "cached"
        else:
            find_all = _uia_attr(root, 'FindAll', 'findAll')
            if find_all is None:
                return [], "no FindAll on element"
            array = find_all(scope, condition)
            reason = "uncached"
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"

    if array is None:
        return [], "FindAll returned nothing"

    length = _uia_attr(array, 'Length', 'length')
    get_element = _uia_attr(array, 'GetElement', 'getElement')
    if length is None or get_element is None:
        return [], "unexpected element array interface"

    elements = []
    for index in range(int(length)):
        try:
            elements.append(get_element(index))
        except Exception:
            break

    return elements, reason


def get_uia_root():
    """Retourne (élément UIA racine de la fenêtre, explication).

    L'élément du premier plan n'est pas toujours un objet UIA : dans ce cas on
    passe par le handle de fenêtre. Retourner l'explication permet de la
    journaliser, faute de quoi un échec de ce chemin reste invisible.
    """
    fg = api.getForegroundObject()
    if not fg:
        return None, "no foreground object"

    element = _element_of(fg)
    if element is not None:
        return element, "foreground UIAElement"

    try:
        client = _client()
        hwnd = getattr(fg, 'windowHandle', None)
        from_handle = _uia_attr(client, 'ElementFromHandle', 'elementFromHandle') if client else None
        if from_handle and hwnd:
            element = from_handle(hwnd)
            if element is not None:
                return element, "ElementFromHandle"
    except Exception as e:
        return None, f"ElementFromHandle failed: {e}"

    return None, "foreground exposes no UIA element"


# ============================================================================
# LECTURE D'UN SOUS-ARBRE EN UN SEUL APPEL
# ============================================================================

SubtreeContent = collections.namedtuple("SubtreeContent", "texts nested_ids")


def element_subtree_content(element, stop_prefix=None, limit=SUBTREE_MAX_ELEMENTS):
    """Textes d'un élément et de ses descendants, en un seul appel.

    ``stop_prefix`` arrête la collecte au premier descendant dont l'AutomationId
    commence par ce préfixe, et compte les suivants : c'est ainsi qu'une ligne
    de pays rend son propre nom sans absorber celui des villes qu'elle contient,
    tout en sachant combien elle en contient.

    FindAll rend les éléments dans l'ordre du document, donc dans l'ordre de
    lecture : le premier texte non vide est le libellé principal.
    """
    if element is None:
        return SubtreeContent([], [])

    cache_request = _shared('subtree', lambda: _build_cache_request((
        _property_id('UIA_NamePropertyId', 30005),
        _property_id('UIA_AutomationIdPropertyId', 30011),
    )))

    elements, reason = _find_all(
        element,
        _tree_scope('TreeScope_Subtree', 7),
        _shared('true', _true_condition),
        cache_request,
    )

    if not elements:
        if DEBUG_MODE:
            log.debug(f"PROTONVPN: empty subtree ({reason})")
        return SubtreeContent([], [])

    texts = []
    nested_ids = []
    stopped = False

    for index, descendant in enumerate(elements[:limit]):
        automation_id = element_automation_id(descendant)

        # index 0 est l'élément lui-même : son propre identifiant ne doit pas
        # être pris pour celui d'un enfant imbriqué.
        if stop_prefix and index > 0 and automation_id.startswith(stop_prefix):
            stopped = True
            nested_ids.append(automation_id)
            continue

        if stopped:
            continue

        name = element_name(descendant).strip()
        if is_speakable(name) and name not in texts:
            texts.append(name)

    return SubtreeContent(texts, nested_ids)


def element_subtree_texts(element, limit=SUBTREE_MAX_ELEMENTS):
    """Liste des textes d'un sous-arbre, sans notion d'imbrication."""
    return element_subtree_content(element, limit=limit).texts


def element_subtree_string(element, limit=SUBTREE_MAX_ELEMENTS):
    """Textes d'un sous-arbre concaténés."""
    return " ".join(element_subtree_texts(element, limit))


def selected_item_text(element):
    """Libellé affiché de l'élément sélectionné dans une liste, ou "".

    Passe par le motif Selection d'UIA pour atteindre l'élément retenu, puis lit
    son contenu — là où ProtonVPN met le texte que l'utilisateur voit, son nom
    ne portant que celui de sa classe interne.
    """
    if element is None:
        return ""

    handler = _uia_handler()
    if handler is None:
        return ""

    pattern_id = getattr(handler, 'UIA_SelectionPatternId', UIA_SELECTION_PATTERN_ID)
    interface = getattr(handler, 'IUIAutomationSelectionPattern', None)
    if interface is None:
        return ""

    try:
        pattern = element.GetCurrentPattern(pattern_id)
        if not pattern:
            return ""
        array = pattern.QueryInterface(interface).GetCurrentSelection()
    except Exception as e:
        log.debugWarning(f"PROTONVPN: selection pattern unavailable: {e}")
        return ""

    if array is None:
        return ""

    length = _uia_attr(array, 'Length', 'length') or 0
    get_element = _uia_attr(array, 'GetElement', 'getElement')
    if not length or get_element is None:
        return ""

    try:
        selected = get_element(0)
    except Exception:
        return ""

    texts = element_subtree_texts(selected)
    return join_item_texts(texts) if texts else ""


def object_subtree_texts(obj, limit=SUBTREE_MAX_ELEMENTS):
    """Textes du sous-arbre d'un NVDAObject, sans en construire d'autres."""
    return element_subtree_texts(_element_of(obj), limit)


def object_subtree_string(obj, limit=SUBTREE_MAX_ELEMENTS):
    return " ".join(object_subtree_texts(obj, limit))


# ============================================================================
# MÉMOIRE COURTE D'UNE ANNONCE
# ============================================================================

# NVDA ne demande pas un libellé une fois par passage du focus. Il vide le cache
# de propriétés de l'objet actif à chaque cycle, puis redemande son nom, sa
# description et son état : l'afficheur braille à chaque rafraîchissement, la
# relecture du focus, le curseur de revue. Un contrôle immobile se faisait donc
# relire plusieurs fois par seconde, et chaque relecture retransférait tout son
# sous-arbre — pour une ligne de pays et ses villes, une centaine d'éléments.
# C'est de là que venait la latence ressentie en parcourant la liste.
#
# La mémoire vit sur le NVDAObject lui-même, hors du cache que NVDA vide, et
# elle expire : ce qu'un contrôle affiche peut changer — le trafic, la charge
# d'un serveur — et une annonce ne doit pas rester en arrière.

MEMO_CONTENT_TTL = 0.5
MEMO_STRUCTURE_TTL = 5.0
MEMO_ATTRIBUTE = "_protonvpnMemo"


def _memo(obj, key, factory, ttl=MEMO_CONTENT_TTL):
    """Valeur mémorisée sur l'objet, recalculée passé ``ttl`` secondes."""
    try:
        store = obj.__dict__.setdefault(MEMO_ATTRIBUTE, {})
    except Exception:
        # Objet sans dictionnaire d'instance : on calcule sans mémoriser.
        return factory()

    now = time.monotonic()
    entry = store.get(key)
    if entry is not None and (now - entry[0]) < ttl:
        return entry[1]

    value = factory()
    store[key] = (now, value)
    return value


def memoized_subtree_texts(obj, limit=SUBTREE_MAX_ELEMENTS):
    """Textes du sous-arbre, relus au plus une fois par demi-seconde."""
    return _memo(obj, ("texts", limit), lambda: object_subtree_texts(obj, limit))


def memoized_subtree_string(obj, limit=SUBTREE_MAX_ELEMENTS):
    return " ".join(memoized_subtree_texts(obj, limit))


# ============================================================================
# RECHERCHE PAR AUTOMATIONID
# ============================================================================

def _desktop_root():
    """Élément racine du bureau, ou None."""
    client = _client()
    get_root = _uia_attr(client, 'GetRootElement', 'getRootElement') if client else None
    if get_root is None:
        return None
    try:
        return get_root()
    except Exception as e:
        log.debugWarning(f"PROTONVPN: no desktop root: {e}")
        return None


def _and_condition(first, second):
    """Conjonction de deux conditions UIA, ou None."""
    if first is None or second is None:
        return None
    client = _client()
    create = _uia_attr(
        client, 'CreateAndCondition', 'createAndCondition'
    ) if client else None
    if create is None:
        return None
    try:
        return create(first, second)
    except Exception as e:
        log.debugWarning(f"PROTONVPN: cannot combine conditions: {e}")
        return None


def find_elements_by_automation_id(automation_id, process_id=None):
    """Éléments UIA portant cet AutomationId. Retourne (liste, explication).

    Un seul appel inter-processus, exécuté côté ProtonVPN, là où un parcours
    récursif en déclenche un par nœud de l'arbre.

    La recherche part de la fenêtre de premier plan. ``process_id`` autorise une
    seconde tentative, limitée à ce processus, lorsque la première ne rend rien :
    voir plus bas pourquoi elle est nécessaire.
    """
    root, reason = get_uia_root()
    if root is None:
        return [], reason

    client = _client()
    create_condition = _uia_attr(
        client, 'CreatePropertyCondition', 'createPropertyCondition'
    ) if client else None
    if create_condition is None:
        return [], "no CreatePropertyCondition on UIA client"

    try:
        condition = create_condition(
            _property_id('UIA_AutomationIdPropertyId', 30011), automation_id
        )
    except Exception as e:
        return [], f"condition failed: {e}"

    # Requête dérivée de celle de NVDA : ces éléments servent à construire des
    # NVDAObjects, qui lisent à la construction des propriétés mises en cache.
    cache_request = _build_cache_request((
        _property_id('UIA_NamePropertyId', 30005),
        _property_id('UIA_BoundingRectanglePropertyId', 30001),
    ), from_base=True)

    descendants = _tree_scope('TreeScope_Descendants', 4)
    elements, find_reason = _find_all(root, descendants, condition, cache_request)

    if elements or not process_id:
        return elements, f"{reason}, {find_reason}"

    # Rien dans la fenêtre de premier plan. Elle n'est pas toujours celle qui
    # porte le contrôle cherché : ProtonVPN ouvre ses infobulles et ses panneaux
    # dans des fenêtres distinctes, et un widget de la colonne droite vit alors
    # dans une autre fenêtre du même processus — hors de portée d'une recherche
    # partie du premier plan.
    #
    # C'est la panne relevée à l'usage, deux fois : « 0 widget(s) found », et
    # vingt secondes plus tard un diagnostic qui les trouvait tous les quatre.
    # On recommence donc depuis le bureau, en restreignant au processus de
    # ProtonVPN : le filtrage est fait par UIA, en un appel, et ce chemin ne
    # coûte quelque chose que lorsque le premier a déjà échoué.
    try:
        scoped = _and_condition(condition, create_condition(
            _property_id('UIA_ProcessIdPropertyId', 30002), int(process_id)
        ))
    except Exception as e:
        return elements, f"{reason}, {find_reason}; process condition failed: {e}"

    if scoped is None:
        return elements, f"{reason}, {find_reason}; no process-wide condition"

    wide, wide_reason = _find_all(
        _desktop_root(), descendants, scoped, cache_request
    )
    return wide, f"{reason}, {find_reason}; process {process_id}: {wide_reason}"


def find_uia_elements(automation_ids, first_only=False, process_id=None):
    """NVDAObjects portant l'un de ces AutomationId.

    Accepte une chaîne ou une suite de chaînes. Un échec est journalisé en
    niveau information, et non en débogage : c'est la seule trace qui dise
    ensuite *pourquoi* un raccourci n'a rien trouvé, et sans elle un échec
    constaté par l'utilisateur reste inexplicable dans le journal qu'il envoie.
    """
    if isinstance(automation_ids, str):
        automation_ids = (automation_ids,)

    objects = []
    reasons = []

    for automation_id in automation_ids:
        elements, reason = find_elements_by_automation_id(automation_id, process_id)
        if not elements:
            reasons.append(f"{automation_id}: {reason}")
            continue
        for element in elements:
            wrapped = wrap_element(element)
            if wrapped is not None:
                objects.append(wrapped)

    if not objects and reasons:
        log.info(
            f"PROTONVPN: no element for {'; '.join(reasons)}"
        )

    if first_only:
        return objects[0] if objects else None
    return objects


def wrap_element(element):
    """Construit un NVDAObject à partir d'un élément UIA, ou None."""
    if element is None:
        return None
    try:
        return UIA(UIAElement=element)
    except Exception as e:
        log.debugWarning(f"PROTONVPN: cannot wrap UIA element: {e}")
        return None


def find_buttons():
    """Boutons de la fenêtre au premier plan, en un seul appel.

    Remplace le parcours récursif qui construisait un NVDAObject par nœud :
    sur la liste des serveurs, cela représentait des milliers d'allers-retours
    inter-processus sur le thread principal de NVDA.
    """
    root, reason = get_uia_root()
    if root is None:
        return []

    client = _client()
    create_condition = _uia_attr(
        client, 'CreatePropertyCondition', 'createPropertyCondition'
    ) if client else None
    if create_condition is None:
        return []

    try:
        condition = create_condition(
            _property_id('UIA_ControlTypePropertyId', 30003), UIA_BUTTON_CONTROL_TYPE
        )
    except Exception as e:
        log.debugWarning(f"PROTONVPN: button condition failed: {e}")
        return []

    cache_request = _build_cache_request((
        _property_id('UIA_NamePropertyId', 30005),
        _property_id('UIA_BoundingRectanglePropertyId', 30001),
    ), from_base=True)

    elements, _reason = _find_all(
        root, _tree_scope('TreeScope_Descendants', 4), condition, cache_request
    )

    buttons = []
    for element in elements[:MAX_SNAPSHOT_ELEMENTS]:
        wrapped = wrap_element(element)
        if wrapped is not None:
            buttons.append(wrapped)
    return buttons


# ============================================================================
# REMONTÉE D'ANCÊTRES (SANS CONSTRUIRE DE NVDAOBJECT)
# ============================================================================

def _parent_walker():
    handler = _uia_handler()
    if handler is None:
        return None
    client = _client()
    return (
        _uia_attr(handler.handler, 'baseTreeWalker')
        or _uia_attr(client, 'RawViewWalker', 'rawViewWalker')
        or _uia_attr(client, 'ControlViewWalker', 'controlViewWalker')
    )


def _walker_cache_request():
    """Requête de cache des pas d'arbre : identifiant, type, nom.

    Sans elle, l'élément rapporté par un pas arrive nu : lire son identifiant
    puis son type coûte deux allers-retours de plus, et un parcours de cinq
    niveaux en paie quinze au lieu de cinq.
    """
    return _shared('walker', lambda: _build_cache_request((
        _property_id('UIA_AutomationIdPropertyId', 30011),
        _property_id('UIA_ControlTypePropertyId', 30003),
        _property_id('UIA_NamePropertyId', 30005),
    )))


# Variantes « BuildCache » qui se sont révélées inutilisables : on ne les
# retente pas, sans quoi chaque pas paierait un échec avant son repli.
_unusable_steps = set()


def _walk(walker, element, cached_names, plain_names):
    """Un pas d'arbre, propriétés utiles embarquées quand c'est possible.

    Si la variante avec cache est refusée, le parcours continue par la variante
    simple : sans ce repli, un refus ferait passer l'arbre pour terminé, et les
    conteneurs cesseraient silencieusement d'être reconnus.
    """
    request = _walker_cache_request()
    if request is not None and cached_names[0] not in _unusable_steps:
        step = _uia_attr(walker, *cached_names)
        if step is not None:
            try:
                return step(element, request)
            except Exception as e:
                _unusable_steps.add(cached_names[0])
                log.debugWarning(
                    f"PROTONVPN: {cached_names[0]} unusable, falling back: {e}"
                )

    step = _uia_attr(walker, *plain_names)
    if step is None:
        return None
    return step(element)


def iter_ancestor_ids(element, max_levels=MAX_ANCESTOR_LEVELS):
    """AutomationId des ancêtres, du plus proche au plus lointain.

    Ne lit que l'AutomationId : aucun nom, donc aucune classe overlay, donc
    aucun risque de ré-entrée. Borné en niveaux, donc en appels.
    """
    walker = _parent_walker()
    if walker is None or element is None:
        return

    current = element
    for _level in range(max_levels):
        try:
            current = _walk(
                walker, current,
                ('GetParentElementBuildCache', 'getParentElementBuildCache'),
                ('GetParentElement', 'getParentElement'),
            )
        except Exception:
            return
        if current is None:
            return
        yield element_automation_id(current)


def nearest_container_id(obj):
    """Conteneur reconnu le plus proche de l'objet, ou "".

    Une seule remontée sert à tous les tests, là où le code précédent en
    lançait une par hypothèse.
    """
    for automation_id in iter_ancestor_ids(_element_of(obj)):
        if automation_id in KNOWN_CONTAINER_IDS:
            return automation_id
        if automation_id.startswith(CONTAINER_CONNECTION_CARD):
            return CONTAINER_CONNECTION_CARD
    return ""


def is_connection_card_element(obj):
    """Vrai si l'objet appartient à la carte de connexion.

    Sans cette restriction, une recherche par libellé retiendrait n'importe quel
    bouton de la fenêtre contenant « connect » — « Connection details »,
    « Reconnect » — et l'add-on invoquerait le mauvais contrôle.
    """
    if get_automation_id(obj).startswith(CONTAINER_CONNECTION_CARD):
        return True
    return any(
        automation_id.startswith(CONTAINER_CONNECTION_CARD)
        for automation_id in iter_ancestor_ids(_element_of(obj))
    )


def previous_unnamed_button_count(element, max_steps=8):
    """Nombre de boutons sans AutomationId précédant l'élément dans sa fratrie.

    Borné : la version précédente remontait la fratrie sans limite, ce qui, dans
    une liste virtualisée, représentait un aller-retour inter-processus par
    frère et pouvait ne jamais rendre la main.
    """
    walker = _parent_walker()
    if walker is None or element is None:
        return -1

    # Aucune des deux orthographes : rendre -1, et non 0, qui passerait pour
    # « aucun frère avant celui-ci » et étiquetterait le bouton par défaut.
    if _uia_attr(
        walker,
        'GetPreviousSiblingElementBuildCache',
        'getPreviousSiblingElementBuildCache',
        'GetPreviousSiblingElement',
        'getPreviousSiblingElement',
    ) is None:
        return -1

    count = 0
    current = element
    for _step in range(max_steps):
        try:
            current = _walk(
                walker, current,
                ('GetPreviousSiblingElementBuildCache',
                 'getPreviousSiblingElementBuildCache'),
                ('GetPreviousSiblingElement', 'getPreviousSiblingElement'),
            )
        except Exception:
            return count
        if current is None:
            return count
        if element_control_type(current) == UIA_BUTTON_CONTROL_TYPE:
            if not element_automation_id(current):
                count += 1
    return count


# ============================================================================
# LIBELLÉS
# ============================================================================

def looks_like_qualified_class_name(text):
    """Vrai si le texte est un nom de classe interne plutôt qu'un libellé."""
    if not text or " " in text:
        return False
    return text.startswith(QUALIFIED_NAME_PREFIX) and "." in text


def looks_like_template_part(text):
    """Vrai si le texte nomme une pièce de gabarit XAML, pas un libellé.

    Un vrai libellé contient des espaces ou ne finit pas par l'un de ces
    suffixes : la condition sur l'espace évite d'écarter une étiquette qui
    parlerait légitimement d'un « bouton content ».
    """
    stripped = (text or "").strip()
    if not stripped or " " in stripped:
        return False
    return stripped.endswith(TEMPLATE_PART_SUFFIXES)


def is_speakable(text):
    """Vrai si le texte mérite d'être annoncé à l'utilisateur.

    Écarte ce que ProtonVPN expose pour son propre compte : noms de classes
    internes et noms de pièces de gabarit. Les laisser passer donnait des
    annonces du genre « Biélorussie, ExpanderButtonContent ».
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    return not (
        looks_like_qualified_class_name(stripped)
        or looks_like_template_part(stripped)
    )


def class_name_segment(text):
    """Dernier segment d'un nom de classe, sans son suffixe technique.

    « ProtonVPN.…​.P2PCountriesComponentViewModel » donne « P2PCountries ».
    """
    segment = text.rsplit(".", 1)[-1]

    for suffix in CLASS_NAME_SUFFIXES:
        if segment.endswith(suffix):
            return segment[: -len(suffix)]

    return segment


def humanize_class_name(text):
    """Transforme un nom de classe interne en libellé lisible."""
    segment = class_name_segment(text)

    label = INTERNAL_NAME_LABELS.get(segment)
    if label:
        return label

    # Repli pour un nom non répertorié : « SecureCoreCountries » devient
    # « Secure Core Countries », toujours préférable au nom complet.
    return split_camel_case(segment) or text


def split_camel_case(text):
    """Insère une espace aux changements de casse.

    « CloseSettings » donne « Close Settings », « VPNPlusOffer » donne
    « VPN Plus Offer » : la seconde règle évite de couper les sigles lettre à
    lettre tout en les séparant du mot qui suit.
    """
    spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)
    spaced = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', spaced)
    return spaced.strip()


def humanize_automation_id(automation_id):
    """Libellé lisible tiré d'un AutomationId.

    « CloseSettingsButton » donne « Close Settings ». Ce libellé reste en
    anglais, puisqu'il vient d'un identifiant interne : il n'est pas traduit,
    mais il nomme le contrôle, là où NVDA n'annoncerait que son rôle.
    """
    name = automation_id
    for suffix in AUTOMATION_ID_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break

    return split_camel_case(name) or automation_id


# Un élément de liste tient parfois son sens de deux fragments : la connexion
# par défaut « États-Unis » se lit « États-Unis, Massachusetts ». On les réunit
# tant qu'ils restent courts — au-delà, le second fragment est une explication,
# qui appartient à la description et non au nom.
ITEM_TEXT_MAX_PARTS = 3
ITEM_TEXT_MAX_PART = 40
ITEM_TEXT_MAX_TOTAL = 90


def join_item_texts(texts):
    """Réunit les fragments courts d'un élément de liste en un seul libellé."""
    kept = []
    total = 0

    for text in texts[:ITEM_TEXT_MAX_PARTS]:
        if len(text) > ITEM_TEXT_MAX_PART:
            break
        if total + len(text) > ITEM_TEXT_MAX_TOTAL:
            break
        kept.append(text)
        total += len(text)

    return ", ".join(kept) if kept else texts[0]


def normalize_for_search(text):
    """Minuscules sans accents, pour un filtre tolérant à la saisie.

    Permet de trouver « Algérie » en tapant « algerie ».
    """
    decomposed = unicodedata.normalize('NFD', text or "")
    stripped = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    return stripped.lower()


def match_widget_label(text):
    """Retourne le libellé du widget correspondant au texte affiché, ou None."""
    haystack = (text or "").lower()
    for keywords, label in WIDGET_DEFINITIONS:
        if any(kw in haystack for kw in keywords):
            return label
    return None


def widget_matches_keywords(obj, keywords, include_automation_id=True):
    """Vérifie qu'un widget porte bien l'un des libellés attendus.

    Sert à identifier un widget par ce qu'il expose plutôt que par son rang :
    l'ordre de la colonne varie selon l'offre et la version de ProtonVPN.

    ``include_automation_id`` doit être mis à False dès que les mots cherchés
    peuvent apparaître dans un identifiant sans désigner le bon contrôle. Le cas
    se présente pour « connect » : tous les boutons de la carte de connexion ont
    un identifiant préfixé « ConnectionCard », si bien que le bouton de
    changement de serveur passait pour le bouton de connexion.
    """
    try:
        parts = [raw_name(obj), object_subtree_string(obj)]
        if include_automation_id:
            parts.append(get_automation_id(obj))
        haystack = " ".join(p for p in parts if p).lower()
        return any(kw in haystack for kw in keywords)
    except Exception as e:
        log.debugWarning(f"PROTONVPN: widget_matches_keywords error: {e}")
        return False


def label_equals_any(obj, labels):
    """Vérifie que le libellé complet de l'objet est exactement l'un des libellés."""
    try:
        label = raw_name(obj).strip().lower()
        if not label:
            texts = object_subtree_texts(obj)
            label = texts[0].strip().lower() if texts else ""
        return label in labels
    except Exception:
        return False


def element_toggle_state(element):
    """État on/off lu sur le motif Toggle d'UIA, ou None.

    Source faisant foi, et la seule disponible pour l'arrêt d'urgence : son
    widget n'affiche que son nom, jamais « activé » ni « désactivé ». Tant que
    l'add-on ne lisait que le texte, l'état d'une protection restait muet.
    """
    if element is None:
        return None

    handler = _uia_handler()
    if handler is None:
        return None

    pattern_id = getattr(handler, 'UIA_TogglePatternId', UIA_TOGGLE_PATTERN_ID)
    interface = getattr(handler, 'IUIAutomationTogglePattern', None)
    if interface is None:
        return None

    try:
        pattern = element.GetCurrentPattern(pattern_id)
        if not pattern:
            return None
        state = _uia_attr(
            pattern.QueryInterface(interface),
            'CurrentToggleState', 'currentToggleState',
        )
    except Exception as e:
        log.debugWarning(f"PROTONVPN: toggle pattern unavailable: {e}")
        return None

    if state == TOGGLE_STATE_ON:
        return True
    if state == TOGGLE_STATE_OFF:
        return False
    # Indéterminé : ne rien affirmer sur une protection.
    return None


def get_widget_state(obj):
    """Lit l'état on/off d'un widget.

    Retourne True (activé), False (désactivé), ou None si l'état n'est pas
    lisible. Le motif Toggle d'UIA passe avant le texte affiché : il dit l'état
    réel du réglage, là où le texte ne le dit que si ProtonVPN a choisi de
    l'écrire — ce qu'il ne fait pas pour l'arrêt d'urgence.
    """
    try:
        state = element_toggle_state(_element_of(obj))
        if state is not None:
            return state

        for text in object_subtree_texts(obj):
            normalized = text.strip().lower().rstrip('.')
            if normalized in WIDGET_STATE_ON:
                return True
            if normalized in WIDGET_STATE_OFF:
                return False
    except Exception as e:
        log.debugWarning(f"PROTONVPN: get_widget_state error: {e}")
    return None


# ============================================================================
# LISTE DES PAYS ET DES VILLES
# ============================================================================

# kind vaut "country" ou "city". country_label porte le pays d'une ville, "" pour
# un pays. nested compte les villes contenues par une ligne de pays.
LocationRow = collections.namedtuple(
    "LocationRow", "automation_id label texts kind country_label nested rect element"
)

KIND_COUNTRY = "country"
KIND_CITY = "city"


def location_code(automation_id):
    """Code pays contenu dans un AutomationId Connect_to_*, en majuscules.

    Vide pour « Pays le plus rapide », qui ne désigne aucun pays : lui attribuer
    les deux premières lettres de « Fastest » le ferait passer pour le pays des
    villes dont le code commence par FA.
    """
    suffix = location_suffix(automation_id)
    if len(suffix) < 2 or FASTEST_ID_FRAGMENT in suffix.lower():
        return ""
    return suffix[:2].upper()


def location_suffix(automation_id):
    """Ce qui suit le préfixe d'un identifiant de ligne, ou "".

    Les lignes portent deux préfixes selon l'état de la connexion : il faut
    retirer celui qui s'applique, pas une longueur fixe.
    """
    for prefix in LOCATION_BUTTON_PREFIXES:
        if automation_id.startswith(prefix):
            return automation_id[len(prefix):]
    return ""


def is_location_button(automation_id):
    """Vrai si l'identifiant est celui d'une ligne de la liste."""
    return automation_id.startswith(LOCATION_BUTTON_PREFIXES)


def is_connected_location(automation_id):
    """Vrai si la ligne est celle de la connexion en cours."""
    return automation_id.startswith(DISCONNECT_LOCATION_PREFIX)


def label_from_automation_id(automation_id):
    """Dernier recours : libellé tiré de l'AutomationId d'une ligne.

    ProtonVPN met le nom de la ville en clair dans l'identifiant
    (Connect_to_Phnom Penh), ce qui donne un repli lisible. Un code pays, lui,
    n'apprend rien : on rend alors l'identifiant tel quel plutôt que « KH ».
    """
    suffix = location_suffix(automation_id)
    if suffix and not COUNTRY_CODE_RE.match(suffix):
        return suffix
    return automation_id


def kind_from_automation_id(automation_id):
    """Nature d'une ligne, déduite de son AutomationId.

    Un code à deux lettres désigne un pays, « Fastest » l'entrée « Pays le plus
    rapide », et tout le reste une ville ou une région : ProtonVPN y met leur
    nom en clair.
    """
    suffix = location_suffix(automation_id)
    if not suffix:
        return KIND_COUNTRY
    if FASTEST_ID_FRAGMENT in suffix.lower():
        return KIND_COUNTRY
    if COUNTRY_CODE_RE.match(suffix):
        return KIND_COUNTRY
    return KIND_CITY


def snapshot_window_elements():
    """Photographie la fenêtre en un seul appel.

    Retourne ([(automationId, name, controlType, rect, element)], explication),
    dans l'ordre du document — donc dans l'ordre de lecture.

    Lire ensuite obj.children ou obj.name élément par élément coûterait un
    aller-retour inter-processus à chaque accès : c'est ce qui gelait NVDA une
    dizaine de secondes sur la liste des pays.
    """
    root, reason = get_uia_root()
    if root is None:
        return [], reason

    cache_request = _build_cache_request((
        _property_id('UIA_NamePropertyId', 30005),
        _property_id('UIA_BoundingRectanglePropertyId', 30001),
    ), from_base=True)

    elements, find_reason = _find_all(
        root, _tree_scope('TreeScope_Descendants', 4), _true_condition(), cache_request
    )
    if not elements:
        return [], f"{reason}, {find_reason}"

    snapshot = []
    for element in elements[:MAX_SNAPSHOT_ELEMENTS]:
        try:
            snapshot.append((
                element_automation_id(element),
                element_name(element),
                element_control_type(element),
                # Cache uniquement : interroger l'application élément par
                # élément sur plusieurs centaines d'éléments annulerait tout le
                # bénéfice de l'appel groupé.
                element_cached_rect(element),
                element,
            ))
        except Exception:
            continue

    return snapshot, f"{reason}, {len(snapshot)} elements"


def _row_texts(snapshot, start, end):
    """Textes situés entre deux lignes consécutives, dédoublonnés."""
    texts = []
    for _id, name, _ct, _rect, _el in snapshot[start + 1:end]:
        cleaned = (name or "").strip()
        if is_speakable(cleaned) and cleaned not in texts:
            texts.append(cleaned)
    return texts


def _group_rows(raw_rows):
    """Classe les lignes, rattache chaque ville à son pays, rétablit l'ordre.

    Dans l'arbre de ProtonVPN, les villes d'un pays précèdent la ligne de ce
    pays : Phnom Penh arrive avant Cambodge, Montréal, Toronto et Vancouver
    avant Canada, les États américains avant États-Unis. Le pays d'une ville est
    donc la première ligne de pays qui la suit — et non celle qui la précède,
    qui est le pays alphabétiquement précédent.

    Les lignes rendues sont réordonnées en pays puis ses villes, c'est-à-dire
    dans l'ordre où l'écran les présente.
    """
    for row in raw_rows:
        row['kind'] = kind_from_automation_id(row['automation_id'])
        row['country_label'] = ""
        row['nested'] = 0

    ordered = []
    pending_cities = []
    last_country = None

    for row in raw_rows:
        if row['kind'] == KIND_CITY:
            pending_cities.append(row)
            continue

        ordered.append(row)
        for city in pending_cities:
            city['country_label'] = row['label']
            ordered.append(city)
        row['nested'] = len(pending_cities)
        pending_cities = []
        last_country = row

    # Villes qu'aucune ligne de pays ne suit : la liste s'arrête au milieu d'un
    # pays déployé. Les rattacher au dernier pays connu reste la meilleure
    # lecture possible, et vaut mieux que de les faire disparaître.
    for city in pending_cities:
        if last_country is not None:
            city['country_label'] = last_country['label']
            last_country['nested'] += 1
        ordered.append(city)

    return ordered


def collect_location_rows(snapshot=None):
    """Lignes de la liste : pays et villes, dans l'ordre d'affichage.

    Une seule photographie de la fenêtre alimente tout : libellés, nature des
    lignes, rattachement des villes à leur pays. Aucun appel supplémentaire par
    ligne, donc aucun risque de gel même sur une liste entièrement déployée.

    La photographie peut être fournie par l'appelant, qui en a parfois déjà une.
    """
    if snapshot is None:
        snapshot, reason = snapshot_window_elements()
    else:
        reason = "snapshot provided"

    if not snapshot:
        log.debug(f"PROTONVPN: no window snapshot ({reason})")
        return []

    indexes = [
        index for index, entry in enumerate(snapshot)
        if is_location_button(entry[0])
    ]
    if not indexes:
        return []

    raw_rows = []
    last_position = len(indexes) - 1

    for position, index in enumerate(indexes[:MAX_LOCATION_ROWS]):
        automation_id, _name, _ct, rect, element = snapshot[index]

        if position < last_position:
            # Fenêtre bornée à droite par la ligne suivante, et plafonnée : une
            # ligne ne doit pas pouvoir adopter le texte d'un panneau voisin.
            end = min(indexes[position + 1], index + 1 + ROW_TEXT_WINDOW)
            texts = _row_texts(snapshot, index, end)
        else:
            # La dernière ligne n'a aucune ligne pour la borner : sa fenêtre
            # courait jusqu'au bout de la fenêtre, panneau de connexion compris.
            # Elle pouvait donc prendre pour libellé l'adresse IP réelle ou
            # l'adresse du compte. Son propre sous-arbre est la seule source
            # sûre, et ne coûte qu'un appel pour une seule ligne.
            texts = []

        if not texts:
            # Rien d'exploitable dans la fenêtre : c'est aussi le cas d'un pays
            # dont la ville imbriquée suit immédiatement dans l'arbre, le nom du
            # pays venant après elle. Le sous-arbre de la ligne, arrêté à la
            # ville, donne le bon nom.
            texts = list(element_subtree_content(
                element, stop_prefix=LOCATION_BUTTON_PREFIXES
            ).texts)

        # Un bouton sans libellé garde un nom tiré de son identifiant : mieux
        # vaut annoncer « Phnom Penh » que de faire disparaître la ligne.
        raw_rows.append({
            'automation_id': automation_id,
            'label': texts[0] if texts else label_from_automation_id(automation_id),
            'texts': texts,
            'rect': rect,
            'element': element,
        })

    raw_rows = _group_rows(raw_rows)

    return [
        LocationRow(
            automation_id=row['automation_id'],
            label=row['label'],
            texts=tuple(row['texts']),
            kind=row['kind'],
            country_label=row['country_label'],
            nested=row['nested'],
            rect=row['rect'],
            element=row['element'],
        )
        for row in raw_rows
    ]


def format_city_count(count):
    """« 3 villes », au singulier ou au pluriel selon la langue."""
    # Traducteurs : nombre de villes disponibles sous un pays.
    return _plural("{count} city", "{count} cities", count).format(count=count)


def format_location(row):
    """Libellé présenté à l'utilisateur pour une ligne de la liste."""
    if row.kind == KIND_CITY and row.country_label:
        # Traducteurs : {country} est le pays, {city} la ville qu'il contient.
        label = _("{country} — {city}").format(
            country=row.country_label, city=row.label
        )
    elif row.kind == KIND_COUNTRY and row.nested:
        label = f"{row.label}, {format_city_count(row.nested)}"
    else:
        label = row.label

    if is_connected_location(row.automation_id):
        # La ligne active : la signaler, c'est dire laquelle on peut quitter.
        return _("{location}, connected").format(location=label)

    return label


# ============================================================================
# VALEURS DYNAMIQUES (IP, PAYS, FOURNISSEUR, TRAFIC)
# ============================================================================

LOCATION_LABEL_TYPES = {0: "ip", 1: "country", 2: "provider"}

SKIPPED_LABELS = frozenset((
    "votre adresse ip", "adresse ip", "ip", "pays", "fournisseur",
    "provider", "country", "your ip address",
))


def get_location_button_label(index):
    """Retourne le label correspondant à l'index du bouton."""
    labels = {
        0: _("Your IP address"),
        1: _("Country"),
        2: _("Provider"),
    }
    return labels.get(index, _("VPN information"))


def extract_value_for_label_type(texts, label_type):
    """Extrait la valeur appropriée depuis une liste de textes."""
    filtered = [
        text.strip() for text in texts
        if text and text.strip() and text.strip().lower() not in SKIPPED_LABELS
    ]
    if not filtered:
        return None

    if label_type == "ip":
        for text in filtered:
            match = IP_REGEX.search(text)
            if match:
                return match.group()
        for text in filtered:
            if any(c.isdigit() for c in text) and "." in text:
                return text

    elif label_type == "country":
        for text in filtered:
            if len(text) <= 30 and not any(c.isdigit() for c in text):
                return text

    elif label_type == "provider":
        for text in filtered:
            if len(text) <= 50:
                return text

    return filtered[0]


CONNECTION_DETAIL_LABELS = {
    "ShowIpFlyoutButton": _("VPN IP address"),
    "ShowVolumeFlyoutButton": _("Total traffic"),
    "ShowServerLoadFlyoutButton": _("Server load"),
    "ShowProtocolFlyoutButton": _("Protocol"),
    "E": _("Current traffic (KB/s)"),
}

# Détails de connexion qui ne sont pas du trafic : étiquetés comme les autres,
# mais écartés du raccourci de trafic.
NON_TRAFFIC_DETAIL_IDS = frozenset((
    "ShowIpFlyoutButton",
    "ShowProtocolFlyoutButton",
))

# Le graphique de trafic courant expose les graduations de son axe vertical
# comme du texte : « 600 », « 300 », « 0 » voisinent avec « 13 Ko/s ». Une
# valeur sans unité ni signe est une graduation, pas une mesure.
VALUE_WITH_UNIT_RE = re.compile(r'[A-Za-zµ%°]')

# Au-delà de deux mesures, on lit le graphique et non plus l'information.
MAX_DETAIL_VALUES = 2

# Mots qui signalent un texte descriptif — l'intitulé d'un détail — et non la
# mesure qui l'accompagne. « protocol » y figure : sans lui, « Protocole » était
# pris pour une valeur et le bouton s'annonçait « Protocole : Protocole ».
#
# Aucune unité ici. « ko/s » y a figuré, pour reconnaître l'intitulé « Trafic
# actuel (Ko/s) » — mais une unité appartient aux mesures : « 16 Ko/s » passait
# alors pour un intitulé et se faisait écarter des valeurs, ne laissant que les
# graduations de l'axe. Cet intitulé se reconnaît de toute façon à « trafic »
# et « actuel ».
DETAIL_LABEL_KEYWORDS = (
    "adresse", "ip", "trafic", "traffic", "volume", "actuel", "total",
    "charge", "load", "protocol",
)


def describes_detail(text, label=""):
    """Vrai si ce texte est l'intitulé d'un détail, et non sa valeur.

    Deux indices : il reprend le libellé attendu, ou il contient un mot qui
    désigne la nature du détail. « Protocole » est un intitulé ;
    « WireGuard (UDP) » est la valeur.
    """
    stripped = (text or "").strip()
    if not stripped:
        return True

    if label and stripped.casefold() == label.strip().casefold():
        return True

    lowered = stripped.lower()
    return any(keyword in lowered for keyword in DETAIL_LABEL_KEYWORDS)


def extract_connection_details(obj):
    """Retourne (libellé, valeurs) d'un bouton ConnectionDetailsPage.

    Le libellé dit la nature du détail (« Trafic total »), les valeurs sont les
    mesures qui l'accompagnent. ProtonVPN les expose dans un ordre qui varie :
    l'intitulé d'abord pour la charge du serveur, la valeur d'abord pour
    l'adresse IP, le protocole et le volume.

    L'intitulé affiché par l'application est préféré au libellé que l'add-on
    connaît : il est dans la langue de l'utilisateur, alors que le nôtre n'est
    traduit que dans les langues où l'add-on l'est. Devant une interface
    espagnole, un add-on non traduit annoncerait « Total traffic ».

    Le libellé connu sert donc de filet, et d'indice pour écarter des valeurs un
    texte qui ne fait que le redire. Sans cela, le protocole s'annonçait
    « Protocole : Protocole » : « Protocole » n'était reconnu ni comme intitulé
    ni comme valeur, si bien qu'il restait dans les deux.
    """
    texts = memoized_subtree_texts(obj)
    automation_id = get_automation_id(obj)
    known_label = CONNECTION_DETAIL_LABELS.get(automation_id)

    if not texts:
        label = known_label or _("VPN info")
        name = raw_name(obj).strip()
        return label, [name] if name else []

    # L'intitulé tel que l'application l'écrit, où qu'il soit dans la liste.
    for index, text in enumerate(texts):
        if describes_detail(text, known_label):
            values = texts[:index] + texts[index + 1:]
            return text, keep_measured_values(values)

    # Aucun intitulé reconnaissable dans ce que l'application affiche : le
    # libellé connu prend le relais, et à défaut le premier texte, plutôt que
    # d'annoncer une mesure sans dire de quoi il s'agit.
    if known_label:
        return known_label, keep_measured_values(texts)

    return texts[0], keep_measured_values(texts[1:])


def keep_measured_values(values):
    """Ne garde que les mesures, et pas plus de deux.

    Le graphique de trafic courant expose les graduations de son axe comme du
    texte : sans ce tri, le raccourci annonçait « Trafic actuel : 13 Ko/s,
    7,4 Ko/s, 600, 300, 0 ». Une valeur qui ne porte ni unité ni signe est une
    graduation.
    """
    measured = [value for value in values if VALUE_WITH_UNIT_RE.search(value)]

    # Aucune valeur n'a d'unité : les rendre telles quelles plutôt que de
    # n'annoncer aucun chiffre du tout.
    if not measured:
        measured = values

    return measured[:MAX_DETAIL_VALUES]


def format_promo_text(texts):
    """Met en forme le texte d'une carte promotionnelle."""
    if not texts:
        return _("VPN Plus offer")

    parts = []
    for text in texts:
        cleaned = text.strip()
        if cleaned and not cleaned.endswith(('.', '!', '?', ':')):
            cleaned += '.'
        parts.append(cleaned)

    result = re.sub(r'\s+', ' ', ' '.join(parts)).strip()
    if "vpn plus" not in result.lower():
        result = "VPN Plus. " + result
    return result


# ============================================================================
# CLASSES OVERLAY
# ============================================================================

class ProtonVPNObject(UIA):
    """Base commune : aucun libellé calculé ne peut en relancer un autre.

    ``_get_name`` des sous-classes passe par ``computed_name``. Si un calcul de
    libellé est déjà en cours plus bas dans la pile — typiquement parce qu'un
    parent lit le contenu de ses enfants — on rend immédiatement le nom brut de
    l'application. C'est ce qui rend impossible la récursion qui faisait planter
    NVDA dans la liste des villes.
    """

    def computed_name(self):  # pragma: no cover - redéfini par les sous-classes
        return super().name

    def _get_name(self):
        with labelling() as first:
            if not first:
                return element_name(_element_of(self))
            try:
                return self.computed_name()
            except Exception as e:
                log.debugWarning(f"PROTONVPN: name computation failed: {e}")
                return element_name(_element_of(self))

    def _get_value(self):
        """Valeur du contrôle, débarrassée des noms de classes internes.

        ProtonVPN nomme les éléments de ses listes déroulantes par leur classe
        interne, et l'API UIA rend le nom de l'élément sélectionné comme valeur
        du contrôle. NVDA annonçait donc, en toutes lettres,
        « ProtonVPN.Client.UI.Main.Settings.Pages.ConnectionPreferences.DefaultConnectionItem ».

        Le libellé que l'utilisateur voit est, lui, dans le contenu de l'élément
        sélectionné : on va le chercher là. Introuvable, on ne rend rien — mieux
        vaut une liste sans valeur annoncée qu'un nom de classe lu à voix haute.
        """
        try:
            raw = super().value or ""
        except Exception:
            return ""

        if not looks_like_qualified_class_name(raw.strip()):
            return raw

        try:
            return selected_item_text(_element_of(self))
        except Exception as e:
            log.debugWarning(f"PROTONVPN: cannot resolve the selected value: {e}")
            return ""


class ProtonVPNLocationRowButton(ProtonVPNObject):
    """Ligne de la liste des emplacements : un pays ou une ville.

    Le libellé vient du contenu réel de la ligne, lu en un seul appel. Les
    villes imbriquées sont comptées mais pas absorbées : une ligne de pays
    annonce son nom et le nombre de villes qu'elle contient, pas le nom de la
    première d'entre elles.
    """

    def _get_locationContent(self):
        return _memo(self, "locationContent", lambda: element_subtree_content(
            _element_of(self), stop_prefix=LOCATION_BUTTON_PREFIXES
        ))

    def computed_name(self):
        content = self.locationContent
        automation_id = get_automation_id(self)

        label = content.texts[0] if content.texts else ""
        if not label:
            label = element_name(_element_of(self)).strip() or automation_id

        city_count = len(content.nested_ids)
        if city_count:
            label = f"{label}, {format_city_count(city_count)}"

        if is_connected_location(automation_id):
            return _("{location}, connected").format(location=label)

        return label

    def _get_description(self):
        """Détails de la ligne : ce qu'elle affiche en plus de son nom.

        Charge utile pour NVDA+Tab (nombre de serveurs, charge, mentions P2P…)
        sans alourdir l'annonce au passage du focus.
        """
        with labelling() as first:
            if not first:
                return super().description
            try:
                extra = [t for t in self.locationContent.texts[1:] if t]
                return ", ".join(extra) if extra else super().description
            except Exception:
                return super().description


class ProtonVPNConnectButton(ProtonVPNObject):
    """Overlay pour le bouton principal Connecter/Déconnecter."""

    def computed_name(self):
        original = element_name(_element_of(self))
        lowered = original.lower()

        if "disconnect" in lowered or "déconnect" in lowered:
            return _("Disconnect VPN")
        if "connect" in lowered:
            return _("Connect VPN")
        if get_automation_id(self) == "ConnectionCardConnectButton":
            return _("Connect VPN")

        return original or _("VPN connection button")


class ProtonVPNLocationDetailsButton(ProtonVPNObject):
    """Overlay pour les boutons dynamiques de LocationDetailsPage."""

    def computed_name(self):
        # La position dans la fratrie ne bouge pas tant que le contrôle vit :
        # elle est mémorisée plus longtemps que le contenu.
        index = _memo(
            self, "siblingIndex",
            lambda: previous_unnamed_button_count(_element_of(self)),
            MEMO_STRUCTURE_TTL,
        )
        label = get_location_button_label(index)
        value = extract_value_for_label_type(
            memoized_subtree_texts(self), LOCATION_LABEL_TYPES.get(index, "unknown")
        )

        result = f"{label} : {value}" if value else label

        if DEBUG_MODE:
            log.debug(f"PROTONVPN: LocationDetailsButton.name → {redact(result)!r}")

        return result


class ProtonVPNConnectionDetailsButton(ProtonVPNObject):
    """Overlay pour les boutons dynamiques de ConnectionDetailsPage."""

    def computed_name(self):
        label, values = extract_connection_details(self)
        result = f"{label} : {', '.join(values)}" if values else label

        if DEBUG_MODE:
            log.debug(f"PROTONVPN: ConnectionDetailsButton.name → {redact(result)!r}")

        return result


class ProtonVPNPromoButton(ProtonVPNObject):
    """Overlay pour les cartes promotionnelles.

    Le nom reste court — c'est lui qui est répété à chaque passage du focus —
    et le texte marketing complet part dans la description, accessible par
    NVDA+Tab sans encombrer la navigation.
    """

    def _get_promoTexts(self):
        return memoized_subtree_texts(self)

    def computed_name(self):
        texts = self.promoTexts
        joined = " ".join(texts).lower()

        if "vpn plus" in joined:
            return _("Upgrade to VPN Plus")

        return texts[0] if texts else _("VPN Plus offer")

    def _get_description(self):
        with labelling() as first:
            if not first:
                return super().description
            try:
                return format_promo_text(self.promoTexts)
            except Exception:
                return super().description


class ProtonVPNWidgetButton(ProtonVPNObject):
    """Overlay pour les widgets colonne droite (NetShield, Kill Switch, etc.).

    Le libellé et l'état sont lus dans ce que le widget affiche. Aucune
    déduction par position : l'ordre de la colonne dépend de l'offre et de la
    version, et une étiquette fausse est plus dangereuse qu'une étiquette
    absente puisqu'elle inspire confiance.
    """

    def _get_widgetState(self):
        return get_widget_state(self)

    def computed_name(self):
        # L'AutomationId identifie le widget sans ambiguïté.
        label = WIDGET_AUTOMATION_IDS.get(get_automation_id(self))

        if label is None:
            original = element_name(_element_of(self))
            label = match_widget_label(f"{original} {memoized_subtree_string(self)}")
            if label is None:
                # Widget non reconnu : conserver ce que fournit l'application.
                label = original.strip() or _("ProtonVPN button")

        return label

    def _get_role(self):
        # Annoncer un bouton bascule laisse NVDA dire « activé »/« désactivé »
        # nativement, dans toutes les langues et en braille.
        if self.widgetState is not None:
            return controlTypes.Role.TOGGLEBUTTON
        return super().role

    def _get_states(self):
        states = set(super().states)
        if self.widgetState:
            states.add(controlTypes.State.PRESSED)
        return states


class ProtonVPNSideWidgetButton(ProtonVPNObject):
    """Overlay pour les boutons à AutomationId connu mais sans libellé."""

    def computed_name(self):
        original = element_name(_element_of(self)).strip()
        if original:
            return original

        automation_id = get_automation_id(self)
        label = SIDE_BUTTON_LABELS.get(automation_id)
        if label:
            return label

        if automation_id:
            return _("Button {}").format(automation_id)

        return _("ProtonVPN button")


class ProtonVPNInternalNameObject(ProtonVPNObject):
    """Overlay pour les éléments nommés par leur classe interne.

    Concerne les onglets de la liste des pays, que ProtonVPN nomme
    « ProtonVPN.Client.UI.Main.….AllCountriesComponentViewModel », et les listes
    déroulantes des paramètres, nommées de la même façon.
    """

    def computed_name(self):
        element = _element_of(self)
        original = element_name(element)

        if not looks_like_qualified_class_name(original):
            return original

        # Les éléments d'une liste portent tous le nom de leur classe : dans les
        # préférences de connexion, les cinq choix s'annonçaient « Default
        # Connection Item », indiscernables les uns des autres. Ce que chacun
        # affiche les distingue, lui — et doit donc passer avant le tableau de
        # libellés connus, qui leur rendrait à nouveau le même nom à tous.
        if element_control_type(element) in ITEM_CONTROL_TYPES:
            texts = memoized_subtree_texts(self)
            if texts:
                return join_item_texts(texts)

        label = INTERNAL_NAME_LABELS.get(class_name_segment(original))
        if label:
            return label

        # Pour un conteneur, son contenu est sa valeur et non son nom : le lire
        # ici ferait annoncer deux fois la même chose.
        return humanize_class_name(original)


class ProtonVPNUnlabelledControl(ProtonVPNObject):
    """Overlay pour tout contrôle que ProtonVPN laisse sans nom accessible.

    Boutons, cases à cocher, boutons radio : l'application n'étiquette pas ces
    contrôles, et le texte qui les désigne à l'écran vit dans leur contenu, pas
    dans leur nom. On le lit là où il est.

    Trois sources, dans cet ordre. Un libellé choisi pour cet identifiant
    précis, quand l'add-on en connaît un : c'est le seul cas où l'on sait mieux
    que le contenu, par exemple pour le bouton Compte, dont le contenu est
    l'adresse du compte et non sa fonction. Puis le contenu du contrôle. Puis
    l'AutomationId mis en mots : « CloseSettingsButton » devient « Close
    settings », ce qui reste informatif là où « Bouton » tout seul ne l'est pas.
    """

    def _get_controlTexts(self):
        return memoized_subtree_texts(self)

    def computed_name(self):
        original = element_name(_element_of(self)).strip()
        if original:
            return original

        automation_id = get_automation_id(self)

        label = AUTOMATION_ID_LABELS.get(automation_id)
        if label:
            return label

        texts = self.controlTexts
        if texts:
            return texts[0]

        if automation_id:
            return humanize_automation_id(automation_id)

        # Rien à offrir : laisser NVDA annoncer le seul rôle plutôt que
        # d'inventer un libellé qui ne correspondrait à rien.
        return ""

    def _get_description(self):
        """Ce que le contrôle affiche en plus de son libellé.

        Les réglages de ProtonVPN font suivre leur intitulé d'une explication
        d'une à trois lignes. Elle n'a pas sa place dans l'annonce au passage du
        focus, mais tout à fait dans la description, lue par NVDA+Tab.
        """
        with labelling() as first:
            if not first:
                return super().description
            try:
                texts = self.controlTexts
                extra = texts[1:] if texts and texts[0] == self.name else texts
                return ", ".join(extra) if extra else super().description
            except Exception:
                return super().description


class ProtonVPNSelectionControl(ProtonVPNUnlabelledControl):
    """Overlay pour les listes déroulantes et autres contrôles à sélection.

    Reprend l'étiquetage des contrôles sans nom, et hérite surtout de la
    réparation de la valeur portée par ``ProtonVPNObject`` : c'est elle qui
    empêche NVDA d'annoncer le nom de classe de l'élément sélectionné.

    S'applique même à un contrôle correctement nommé, puisque le défaut est dans
    sa valeur et non dans son nom.
    """


# ============================================================================
# DIALOGUE DE SELECTION
# ============================================================================

if GUI_AVAILABLE:

    class LocationSelectionDialog(wx.Dialog):
        """Liste filtrable des pays et des villes.

        Évite de parcourir des dizaines de lignes à la flèche : on tape
        quelques lettres et on valide. Le filtre porte sur le pays comme sur la
        ville, « johan » comme « afrique » menant à Johannesbourg.
        """

        def __init__(self, parent, rows, on_select, initial_filter=""):
            super().__init__(parent, title=_("Connect to a country or a city"))

            self._rows = rows
            self._filtered = list(rows)
            self._on_select = on_select

            mainSizer = wx.BoxSizer(wx.VERTICAL)

            mainSizer.Add(
                wx.StaticText(self, label=_("&Filter:")),
                flag=wx.ALL, border=5,
            )
            self._filterCtrl = wx.TextCtrl(self)
            mainSizer.Add(self._filterCtrl, flag=wx.EXPAND | wx.ALL, border=5)

            mainSizer.Add(
                wx.StaticText(self, label=_("Countries and cit&ies:")),
                flag=wx.ALL, border=5,
            )
            self._listBox = wx.ListBox(self, style=wx.LB_SINGLE, size=(360, 280))
            mainSizer.Add(self._listBox, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

            buttonSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
            if buttonSizer:
                mainSizer.Add(buttonSizer, flag=wx.EXPAND | wx.ALL, border=5)

            self.SetSizerAndFit(mainSizer)

            self._filterCtrl.Bind(wx.EVT_TEXT, self._onFilterChanged)
            self._listBox.Bind(wx.EVT_LISTBOX_DCLICK, self._onOk)
            self.Bind(wx.EVT_BUTTON, self._onOk, id=wx.ID_OK)

            if initial_filter:
                # ChangeValue et non SetValue : déclencher EVT_TEXT avant que la
                # liste n'existe produirait une première mise à jour à vide.
                self._filterCtrl.ChangeValue(initial_filter)
                self._applyFilter()

            self._refreshList()
            self._filterCtrl.SetFocus()

        def _refreshList(self):
            self._listBox.Set([format_location(row) for row in self._filtered])
            if self._filtered:
                self._listBox.SetSelection(0)

        def _applyFilter(self):
            needle = normalize_for_search(self._filterCtrl.GetValue())
            if not needle:
                self._filtered = list(self._rows)
                return
            self._filtered = [
                row for row in self._rows
                if needle in normalize_for_search(format_location(row))
            ]

        def _onFilterChanged(self, event):
            self._applyFilter()
            self._refreshList()

        def _onOk(self, event):
            index = self._listBox.GetSelection()
            if index == wx.NOT_FOUND or index >= len(self._filtered):
                wx.Bell()
                return

            row = self._filtered[index]
            callback = self._on_select
            self.Destroy()

            # Activer après fermeture : le focus doit être revenu à ProtonVPN
            # pour que l'activation aboutisse.
            wx.CallLater(100, callback, row)


# ============================================================================
# CLASSE APPMODULE
# ============================================================================
log.info("PROTONVPN: Defining AppModule class...")


class AppModule(appModuleHandler.AppModule):
    """Module d'application NVDA pour ProtonVPN."""

    scriptCategory = "ProtonVPN"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        log.info(f"PROTONVPN: AppModule v{get_addon_version()} loaded (DEBUG_MODE={DEBUG_MODE})")
        if DEBUG_MODE:
            ui.message(_("ProtonVPN add-on active"))

    def _search(self, automation_ids, first_only=False):
        """Recherche par identifiant, élargie au processus si le premier plan échoue.

        La fenêtre de premier plan n'est pas toujours celle qui porte le
        contrôle cherché. Transmettre le PID autorise la seconde tentative,
        qui ne coûte quelque chose que lorsque la première n'a rien rendu.
        """
        return find_uia_elements(
            automation_ids, first_only=first_only,
            process_id=getattr(self, 'processID', None),
        )

    def _search_elements(self, automation_id):
        """Éléments bruts portant cet identifiant, et l'explication d'un échec."""
        return find_elements_by_automation_id(
            automation_id, process_id=getattr(self, 'processID', None)
        )

    # ========================================================================
    # CLASSIFICATION DES OBJETS
    # ========================================================================

    def chooseNVDAObjectOverlayClasses(self, obj, clsList):
        """Choisit les classes overlay appropriées.

        Appelée pour chaque objet que NVDA construit : tout ce qui est fait ici
        est payé des milliers de fois en parcourant une liste. D'où l'ordre
        retenu — l'AutomationId d'abord, qui ne coûte rien, puis une unique
        remontée d'ancêtres — et l'absence totale de lecture de nom ou de
        parcours de descendants, qui rouvriraient la boucle de ré-entrée.
        """
        try:
            element = _element_of(obj)
            if element is None or element_framework_id(element) != "XAML":
                super().chooseNVDAObjectOverlayClasses(obj, clsList)
                return

            automation_id = get_automation_id(obj)

            control_type = element_control_type(element)
            is_button = control_type == UIA_BUTTON_CONTROL_TYPE

            if is_location_button(automation_id):
                clsList.insert(0, ProtonVPNLocationRowButton)
            elif automation_id in WIDGET_AUTOMATION_IDS:
                clsList.insert(0, ProtonVPNWidgetButton)
            elif automation_id == "ConnectionCardConnectButton":
                clsList.insert(0, ProtonVPNConnectButton)
            elif automation_id in SIDE_BUTTON_LABELS:
                clsList.insert(0, ProtonVPNSideWidgetButton)
            elif is_button and automation_id in CONNECTION_DETAIL_LABELS:
                # Adresse IP du VPN et compteurs de trafic : ces boutons-là
                # portent leur propre AutomationId, inutile de remonter l'arbre.
                clsList.insert(0, ProtonVPNConnectionDetailsButton)
            elif (
                looks_like_qualified_class_name(element_name(element))
                and control_type not in SELECTION_CONTROL_TYPES
            ):
                clsList.insert(0, ProtonVPNInternalNameObject)

            elif control_type in SELECTION_CONTROL_TYPES:
                # Une liste est reprise même lorsqu'elle porte un nom : ce n'est
                # pas son nom qui pose problème mais sa valeur, où l'API UIA
                # rend le nom de classe de l'élément sélectionné.
                clsList.insert(0, ProtonVPNSelectionControl)

            elif (
                control_type in INTERACTIVE_CONTROL_TYPES
                and not element_name(element).strip()
            ):
                # Tout contrôle sans nom sur lequel l'utilisateur peut se
                # déplacer, et non les seuls boutons : ProtonVPN laisse aussi
                # des cases à cocher et des boutons radio sans nom dans ses
                # paramètres, et ceux-là ne recevaient rien du tout.
                #
                # La remontée d'ancêtres sert aux boutons dont la page dit ce
                # qu'ils sont. Un identifiant qui porte déjà son libellé en
                # toutes pages — « Fermer les paramètres », « Compte » — n'en a
                # pas besoin : voir PAGE_INDEPENDENT_LABEL_IDS.
                needs_container = (
                    is_button and automation_id not in PAGE_INDEPENDENT_LABEL_IDS
                )
                container = nearest_container_id(obj) if needs_container else ""

                if container == CONTAINER_CONNECTION_DETAILS:
                    clsList.insert(0, ProtonVPNConnectionDetailsButton)
                elif container == CONTAINER_LOCATION_DETAILS:
                    clsList.insert(0, ProtonVPNLocationDetailsButton)
                elif container == CONTAINER_OVERLAY:
                    clsList.insert(0, ProtonVPNPromoButton)
                else:
                    clsList.insert(0, ProtonVPNUnlabelledControl)

        except Exception as e:
            log.error(f"PROTONVPN: chooseNVDAObjectOverlayClasses error: {e}")

        super().chooseNVDAObjectOverlayClasses(obj, clsList)

    # ========================================================================
    # ACTIVATION D'UN ÉLÉMENT
    # ========================================================================

    def _find_element_by_automation_id(self, target_id):
        """Recherche un élément par AutomationId. Retourne le NVDAObject ou None."""
        return self._search(target_id, first_only=True)

    def _invoke_via_pattern(self, obj, pattern_id_name, interface_name, method_name):
        """Déclenche un élément via un pattern UIA. Retourne True en cas de succès."""
        try:
            element = _element_of(obj)
            if element is None:
                return False

            handler = _uia_handler()
            if handler is None:
                return False

            pattern_id = getattr(handler, pattern_id_name, None)
            interface = getattr(handler, interface_name, None)
            if pattern_id is None or interface is None:
                return False

            pattern = element.GetCurrentPattern(pattern_id)
            if not pattern:
                return False

            getattr(pattern.QueryInterface(interface), method_name)()
            return True
        except Exception as e:
            log.debugWarning(f"PROTONVPN: {method_name} pattern unavailable: {e}")
            return False

    def _invoke_via_keyboard(self, obj):
        """Dernier recours : donner le focus à l'élément puis envoyer Entrée.

        Utilise KeyboardInputGesture (SendInput) et non winUser.sendMessage :
        SendMessage est synchrone et inter-processus, il bloquerait le thread
        principal de NVDA tant que ProtonVPN ne traite pas le message — ce qui
        arrive précisément pendant l'établissement d'une connexion. Les fenêtres
        XAML ignorent de toute façon les WM_KEYDOWN synthétiques.
        """
        try:
            obj.setFocus()
        except Exception as e:
            log.debugWarning(f"PROTONVPN: setFocus failed: {e}")
            return False

        # Vérifier que le focus a bien atterri sur l'élément visé avant
        # d'envoyer la touche. Sans ce contrôle, un setFocus refusé laissait
        # partir une Entrée sur ce qui avait le focus auparavant, c'est-à-dire
        # sur n'importe quoi : un bouton de déconnexion, une confirmation.
        if not self._focus_is_on(obj):
            log.debugWarning(
                "PROTONVPN: focus did not reach the target, no key sent"
            )
            return False

        try:
            from keyboardHandler import KeyboardInputGesture
            KeyboardInputGesture.fromName("enter").send()
            return True
        except Exception as e:
            log.error(f"PROTONVPN: keyboard fallback failed: {e}")
            return False

    @staticmethod
    def _focus_is_on(obj):
        """Vrai si l'élément UIA au focus est bien celui-ci.

        Interroge UIA plutôt que NVDA : le focus de NVDA est mis à jour par
        événement, donc en retard d'un instant sur un setFocus qui vient
        d'aboutir.
        """
        client = _client()
        element = _element_of(obj)
        if client is None or element is None:
            return False

        get_focused = _uia_attr(client, 'GetFocusedElement', 'getFocusedElement')
        compare = _uia_attr(client, 'CompareElements', 'compareElements')
        if get_focused is None or compare is None:
            return False

        try:
            return bool(compare(get_focused(), element))
        except Exception as e:
            log.debugWarning(f"PROTONVPN: cannot compare the focused element: {e}")
            return False

    def _invoke_element(self, obj):
        """Déclenche un élément, du moyen le plus fiable au moins fiable."""
        if obj is None:
            return False

        if self._invoke_via_pattern(
            obj, "UIA_InvokePatternId", "IUIAutomationInvokePattern", "Invoke"
        ):
            return True

        # Les widgets de la colonne droite exposent souvent TogglePattern
        # plutôt qu'InvokePattern.
        if self._invoke_via_pattern(
            obj, "UIA_TogglePatternId", "IUIAutomationTogglePattern", "Toggle"
        ):
            return True

        try:
            obj.doAction()
            return True
        except Exception as e:
            log.debugWarning(f"PROTONVPN: doAction failed: {e}")

        return self._invoke_via_keyboard(obj)

    # ========================================================================
    # CONNEXION / DÉCONNEXION
    # ========================================================================

    def _find_connection_button_by_label(self):
        """Repli : localiser le bouton principal par son libellé.

        Retourne (bouton, is_disconnecting) ou None.

        Deux niveaux, du plus sûr au moins sûr. D'abord les boutons de la carte
        de connexion, où une recherche par sous-chaîne est sans danger. Ensuite,
        hors de la carte, uniquement une correspondance de libellé complet.

        Dans les deux cas, tous les candidats sont examinés pour « déconnecter »
        avant « connecter » : le second est contenu dans le premier, et retenir
        le premier bouton rencontré ferait passer « Connection details » pour le
        bouton de connexion.
        """
        buttons = find_buttons()

        # Sur le libellé affiché seulement : l'identifiant de ces boutons
        # commence par « ConnectionCard », qui contient « connect ».
        card = [b for b in buttons if is_connection_card_element(b)]
        for obj in card:
            if widget_matches_keywords(obj, DISCONNECT_KEYWORDS, False):
                return obj, True
        for obj in card:
            if widget_matches_keywords(obj, CONNECT_KEYWORDS, False):
                return obj, False

        for obj in buttons:
            if label_equals_any(obj, DISCONNECT_LABELS):
                return obj, True
        for obj in buttons:
            if label_equals_any(obj, CONNECT_LABELS):
                return obj, False

        if DEBUG_MODE:
            labels = [redact(raw_name(b).strip()) for b in buttons if raw_name(b).strip()]
            log.debug(f"PROTONVPN: no connection button matched. Buttons: {labels}")

        return None

    def _connection_state(self):
        """État du VPN : True connecté, False déconnecté, None indéterminé."""
        if self._find_element_by_automation_id("ConnectionCardDisconnectButton"):
            return True
        if self._find_element_by_automation_id("ConnectionCardConnectButton"):
            return False
        return None

    @script(
        # Traducteurs : description du raccourci dans Gestes de commandes.
        description=_("Toggle VPN connection"),
        gesture="kb:control+shift+d",
    )
    def script_toggleVPN(self, gesture):
        log.debug("PROTONVPN: script_toggleVPN triggered")

        btn = self._find_element_by_automation_id("ConnectionCardDisconnectButton")
        is_disconnecting = True

        if not btn:
            btn = self._find_element_by_automation_id("ConnectionCardConnectButton")
            is_disconnecting = False

        if not btn:
            log.debug("PROTONVPN: AutomationId lookup failed, searching by label")
            result = self._find_connection_button_by_label()
            if result:
                btn, is_disconnecting = result

        if not btn:
            ui.message(_("Connection button not found"))
            log.error("PROTONVPN: Neither Connect nor Disconnect button found")
            return

        ui.message(_("Disconnecting") if is_disconnecting else _("Connecting"))

        # Le bouton trouvé indique l'état de départ : Déconnecter n'est présent
        # que si le VPN est connecté.
        previous_state = is_disconnecting

        if self._invoke_element(btn):
            self._schedule(VPN_STATE_POLL_MS, self._confirm_vpn_state, previous_state)
        else:
            ui.message(_("Action unavailable"))

    @staticmethod
    def _schedule(delay_ms, callback, *args):
        """Programme un rappel sur le thread principal, si wx est disponible."""
        if not GUI_AVAILABLE:
            return False
        try:
            wx.CallLater(delay_ms, callback, *args)
            return True
        except Exception as e:
            log.debugWarning(f"PROTONVPN: cannot schedule callback: {e}")
            return False

    def _confirm_vpn_state(self, previous_state, attempt=1):
        """Annonce le nouvel état du VPN une fois le changement constaté.

        Sonde plusieurs fois : une connexion ProtonVPN dépasse régulièrement une
        seconde et demie. Surtout, on compare à l'état de départ au lieu de
        tester la simple présence d'un bouton — sinon on confirmerait une
        action qui n'a pas eu lieu.
        """
        try:
            state = self._connection_state()

            if state is not None and state != previous_state:
                ui.message(_("VPN connected") if state else _("VPN disconnected"))
                log.debug(f"PROTONVPN: state change confirmed after {attempt} attempt(s)")
                return

            if attempt >= VPN_STATE_MAX_ATTEMPTS:
                # Ne pas rester muet : l'utilisateur a demandé une action et
                # doit savoir qu'elle n'a pas abouti.
                ui.message(_("VPN state unchanged"))
                log.debug("PROTONVPN: no state change observed")
                return

            self._schedule(
                VPN_STATE_POLL_MS, self._confirm_vpn_state, previous_state, attempt + 1
            )
        except Exception as e:
            log.error(f"PROTONVPN: _confirm_vpn_state error: {e}")

    # ========================================================================
    # WIDGETS
    # ========================================================================

    def _iter_widget_buttons(self):
        """Énumère les widgets de la colonne droite."""
        return self._search(tuple(WIDGET_AUTOMATION_IDS))

    def _find_widget_by_keywords(self, keywords):
        """Retourne le widget portant l'un des libellés donnés, ou None."""
        for widget in self._iter_widget_buttons():
            if widget_matches_keywords(widget, keywords):
                return widget
        return None

    def _announce_widget_state(self, automation_id, keywords, label):
        """Relit et annonce l'état d'un widget après basculement.

        Retrouve le widget par son identifiant exact, comme l'a fait le
        basculement lui-même. Repasser par les libellés ici exposait à annoncer
        l'état d'un autre widget sous le nom de celui-ci : pour un réglage de
        sécurité, une assurance fausse est pire qu'une absence d'annonce.
        """
        try:
            widget = self._search(automation_id, first_only=True)
            if widget is None:
                widget = self._find_widget_by_keywords(keywords)
            state = get_widget_state(widget) if widget else None

            if state is None:
                # État illisible : annoncer le widget sans affirmer un résultat
                # qui n'a pas été vérifié.
                ui.message(label)
            elif state:
                ui.message(_("{feature} enabled").format(feature=label))
            else:
                ui.message(_("{feature} disabled").format(feature=label))
        except Exception as e:
            log.error(f"PROTONVPN: _announce_widget_state error: {e}")
            ui.message(label)

    @script(
        # Traducteurs : description du raccourci dans Gestes de commandes.
        description=_("Toggle Kill Switch"),
        gesture="kb:control+shift+k",
    )
    def script_toggleKillSwitch(self, gesture):
        """Bascule l'arrêt d'urgence, sans s'arrêter à ses réglages.

        Le widget de la colonne droite n'est pas un interrupteur : l'activer
        ouvre la page de réglage, et le raccourci s'arrêtait là, sans même y
        placer le curseur. Or l'interrupteur, lui, s'appelle KillSwitchToggle et
        porte le motif Toggle d'UIA.

        Les deux ne coexistent pas : sur la page principale, seul le widget
        existe ; la page ouverte, seul l'interrupteur existe. D'où la marche à
        suivre : basculer l'interrupteur s'il est déjà là, sinon ouvrir la page
        par le widget puis basculer, une fois la page affichée.
        """
        log.debug("PROTONVPN: script_toggleKillSwitch triggered")

        try:
            toggle = self._search(
                KILL_SWITCH_TOGGLE_AUTOMATION_ID, first_only=True
            )
            if toggle is not None:
                self._flipKillSwitch(toggle)
                return

            # Identifiant exact d'abord : sans ambiguïté et sans heuristique.
            widget = self._search(KILL_SWITCH_AUTOMATION_ID, first_only=True)
            if widget is None:
                widget = self._find_widget_by_keywords(KILL_SWITCH_KEYWORDS)

            if widget is None:
                # Ni l'interrupteur ni le widget. Cela arrive dans un cas
                # précis, relevé à l'usage : les paramètres sont ouverts sur une
                # autre page que celle de l'arrêt d'urgence. La colonne droite a
                # alors disparu avec ses widgets, et l'interrupteur n'existe que
                # sur sa propre page. Le dire, plutôt que de laisser croire à
                # une panne.
                #
                # Aucun repli par position ici. Il a existé, et il était
                # dangereux : _invoke_element tente Toggle juste après Invoke,
                # si bien qu'une position fausse ne se contentait pas d'ouvrir
                # le mauvais panneau, elle pouvait basculer un autre réglage de
                # sécurité — NetShield, le tunnel divisé — sans que
                # l'utilisateur l'ait demandé ni l'entende.
                self._log_widget_diagnostics(
                    self._iter_widget_buttons(), "Kill Switch not identified"
                )

                settings_open = self._settings_are_open()
                log.info(
                    "PROTONVPN: Kill Switch not reachable, settings page open:"
                    f" {settings_open}"
                )

                if settings_open:
                    ui.message(_("Kill Switch unavailable here, go back first"))
                else:
                    ui.message(_("Kill Switch not found"))
                return

            if not self._invoke_element(widget):
                ui.message(_("Action unavailable"))
                return

            # La page de réglage s'ouvre : y chercher l'interrupteur, puis le
            # basculer. Sans cette seconde étape, le raccourci laissait
            # l'utilisateur devant un panneau, sans avoir rien changé.
            if not self._schedule(SETTINGS_PAGE_DELAY_MS, self._flipKillSwitchWhenReady):
                ui.message(_("Kill Switch"))
        except Exception as e:
            log.error(f"PROTONVPN: script_toggleKillSwitch error: {e}")
            ui.message(_("Action unavailable"))

    def _settings_are_open(self):
        """Vrai si la fenêtre affiche les paramètres.

        Reconnue au bouton qui les ferme : il n'existe que là. Sert à distinguer
        « l'add-on ne trouve pas le contrôle » de « le contrôle n'est pas
        joignable depuis cet écran », qui n'appellent pas la même conduite.
        """
        elements, _reason = self._search_elements(
            CLOSE_SETTINGS_AUTOMATION_ID
        )
        return bool(elements)

    def _flipKillSwitchWhenReady(self):
        """Bascule l'interrupteur une fois la page de réglage affichée."""
        toggle = self._search(KILL_SWITCH_TOGGLE_AUTOMATION_ID, first_only=True)

        if toggle is None:
            # La page ne s'est pas ouverte, ou pas assez vite. Ne rien forcer :
            # dire où l'on en est vaut mieux qu'agir au hasard sur un réglage de
            # sécurité.
            log.debug("PROTONVPN: the Kill Switch toggle did not appear")
            ui.message(_("Kill Switch settings opened"))
            return

        self._flipKillSwitch(toggle)

    def _flipKillSwitch(self, toggle):
        """Bascule l'interrupteur, y place le curseur, puis annonce l'état.

        Le curseur est placé sur l'interrupteur : l'utilisateur se retrouve sur
        le contrôle qu'il vient de changer, et peut le rebasculer sans le
        chercher.
        """
        if not self._invoke_element(toggle):
            ui.message(_("Action unavailable"))
            return

        try:
            toggle.setFocus()
        except Exception as e:
            log.debugWarning(f"PROTONVPN: cannot focus the Kill Switch toggle: {e}")

        # L'état résultant est relu sur l'interrupteur lui-même : ne jamais
        # annoncer un basculement qui n'a pas été constaté.
        scheduled = self._schedule(
            WIDGET_STATE_POLL_MS,
            self._announce_widget_state,
            KILL_SWITCH_TOGGLE_AUTOMATION_ID,
            KILL_SWITCH_KEYWORDS,
            _("Kill Switch"),
        )
        if not scheduled:
            ui.message(_("Kill Switch"))

    # ========================================================================
    # PAYS ET VILLES
    # ========================================================================

    @script(
        # Traducteurs : description du raccourci dans Gestes de commandes.
        description=_("Search for a country"),
        gesture="kb:control+shift+l",
    )
    def script_connectToCountry(self, gesture):
        """Place le curseur dans le champ de recherche de ProtonVPN.

        Ce champ filtre la liste complète, y compris les pays que l'interface
        n'a pas encore matérialisés.

        Le nom de la méthode est conservé tel quel malgré ce qu'elle fait
        vraiment : NVDA retient les gestes personnalisés par nom de script, et
        le renommer effacerait silencieusement le raccourci que l'utilisateur
        s'est éventuellement choisi.
        """
        log.debug("PROTONVPN: script_connectToCountry triggered")

        search_box = self._search(SEARCH_BOX_AUTOMATION_ID, first_only=True)
        if search_box is None:
            ui.message(_("Country search unavailable"))
            return

        try:
            search_box.setFocus()
            ui.message(_("Country search"))
        except Exception as e:
            log.debugWarning(f"PROTONVPN: cannot focus the search box: {e}")
            ui.message(_("Action unavailable"))

    def _focused_country_label(self):
        """Pays de la ligne qui a le focus, pour préfiltrer la liste."""
        try:
            focus = api.getFocusObject()
        except Exception:
            return ""

        if focus is None:
            return ""

        automation_id = get_automation_id(focus)
        if not is_location_button(automation_id):
            return ""

        content = element_subtree_content(
            _element_of(focus), stop_prefix=LOCATION_BUTTON_PREFIXES
        )
        return content.texts[0] if content.texts else ""

    @script(
        # Traducteurs : description du raccourci dans Gestes de commandes.
        description=_("List countries and cities"),
        gesture="kb:control+shift+o",
    )
    def script_listLocations(self, gesture):
        """Ouvre la liste filtrable des pays et des villes affichés."""
        log.debug("PROTONVPN: script_listLocations triggered")

        if not GUI_AVAILABLE:
            ui.message(_("Action unavailable"))
            return

        try:
            rows = collect_location_rows()
        except Exception as e:
            log.error(f"PROTONVPN: cannot read the location list: {e}")
            ui.message(_("Country list unavailable"))
            return

        if not rows:
            ui.message(_("Country list unavailable"))
            return

        initial_filter = self._focused_country_label()
        log.debug(
            f"PROTONVPN: {len(rows)} location row(s), "
            f"{sum(1 for r in rows if r.kind == KIND_CITY)} cit(y/ies)"
        )

        wx.CallAfter(self._showLocationDialog, rows, initial_filter)

    def _showLocationDialog(self, rows, initial_filter=""):
        """Affiche le dialogue sur le thread principal de NVDA."""
        try:
            gui.mainFrame.prePopup()
            try:
                dialog = LocationSelectionDialog(
                    gui.mainFrame, rows, self._connectToLocation, initial_filter
                )
                dialog.Show()
            finally:
                gui.mainFrame.postPopup()
        except Exception as e:
            log.error(f"PROTONVPN: location dialog failed: {e}")
            ui.message(_("Action unavailable"))

    def _connectToLocation(self, row):
        """Active la ligne choisie dans le dialogue.

        L'élément a été saisi à l'ouverture de la liste, et le dialogue ne
        bloque pas : ProtonVPN a pu recycler ses lignes entre-temps, la liste
        étant virtualisée. On revérifie donc l'identifiant de l'élément avant de
        l'invoquer — se connecter à un autre pays que celui annoncé serait le
        pire des résultats pour un VPN, et le plus silencieux.
        """
        current_id = element_current_automation_id(row.element)

        if current_id != row.automation_id:
            log.debug(
                f"PROTONVPN: row changed since the list was built "
                f"({row.automation_id!r} is now {current_id!r})"
            )
            ui.message(_("The list has changed, open it again"))
            return

        obj = wrap_element(row.element)
        if obj is None:
            ui.message(_("Action unavailable"))
            return

        # Activer la ligne en cours déconnecte, elle ne reconnecte pas :
        # l'annoncer comme une connexion dirait l'inverse de ce qui se passe.
        if is_connected_location(row.automation_id):
            ui.message(_("Disconnecting from {location}").format(location=row.label))
        else:
            ui.message(
                _("Connecting to {location}").format(location=format_location(row))
            )

        if not self._invoke_element(obj):
            ui.message(_("Action unavailable"))

    # ========================================================================
    # TRAFIC
    # ========================================================================

    def _find_buttons_in(self, container_automation_id):
        """Boutons contenus dans la page portant cet AutomationId.

        La page est localisée par son identifiant, puis seul son sous-arbre est
        interrogé — un appel, pas un parcours.
        """
        page = self._find_element_by_automation_id(container_automation_id)
        if not page:
            return []

        client = _client()
        create_condition = _uia_attr(
            client, 'CreatePropertyCondition', 'createPropertyCondition'
        ) if client else None
        if create_condition is None:
            return []

        try:
            condition = create_condition(
                _property_id('UIA_ControlTypePropertyId', 30003),
                UIA_BUTTON_CONTROL_TYPE,
            )
        except Exception as e:
            log.debugWarning(f"PROTONVPN: button condition failed: {e}")
            return []

        cache_request = _build_cache_request((
            _property_id('UIA_NamePropertyId', 30005),
            _property_id('UIA_BoundingRectanglePropertyId', 30001),
        ), from_base=True)

        elements, _reason = _find_all(
            _element_of(page),
            _tree_scope('TreeScope_Descendants', 4),
            condition,
            cache_request,
        )

        buttons = []
        for element in elements:
            wrapped = wrap_element(element)
            if wrapped is not None:
                buttons.append(wrapped)
        return buttons

    @script(
        # Traducteurs : description du raccourci dans Gestes de commandes.
        description=_("Announce traffic information"),
        gesture="kb:control+shift+t",
    )
    def script_announceTraffic(self, gesture):
        log.debug("PROTONVPN: script_announceTraffic triggered")

        try:
            traffic_info = []

            # Tous les boutons de la page de détails, et non deux identifiants
            # choisis d'avance : les relevés en VPN connecté ont montré un
            # ShowServerLoadFlyoutButton que l'add-on ignorait. Lire la page
            # entière fait remonter ce qu'elle contient, connu ou non.
            for obj in self._find_buttons_in(CONTAINER_CONNECTION_DETAILS):
                if get_automation_id(obj) in NON_TRAFFIC_DETAIL_IDS:
                    continue
                label, values = extract_connection_details(obj)
                if values:
                    traffic_info.append(f"{label} : {', '.join(values)}")

            if traffic_info:
                message = ". ".join(traffic_info)
                ui.message(message)
                log.debug(f"PROTONVPN: Traffic announced: {redact(message)}")
            else:
                ui.message(_("Traffic information unavailable. VPN not connected?"))
        except Exception as e:
            log.error(f"PROTONVPN: script_announceTraffic error: {e}")
            ui.message(_("Action unavailable"))

    # ========================================================================
    # DIAGNOSTIC
    # ========================================================================

    def _log_widget_diagnostics(self, widgets, reason=""):
        """Consigne tout ce que chaque widget expose.

        Journalisé en niveau info, sans DEBUG_MODE : c'est la seule façon de
        savoir sous quel libellé ProtonVPN présente réellement ses widgets et
        d'ajuster WIDGET_DEFINITIONS en conséquence.
        """
        try:
            log.info(f"PROTONVPN DIAG: {len(widgets)} widget(s) found. {reason}")
            for index, widget in enumerate(widgets):
                try:
                    # Les motifs disent si le widget porte lui-même son état :
                    # c'est ce qui permettrait d'annoncer l'arrêt d'urgence
                    # depuis la page principale, sans ouvrir ses réglages.
                    patterns = self._available_patterns(_element_of(widget))
                    log.info(
                        f"PROTONVPN DIAG: [{index}] "
                        f"automationId={get_automation_id(widget)!r} "
                        f"name={redact(raw_name(widget))!r} "
                        f"toggleState={element_toggle_state(_element_of(widget))} "
                        f"patterns={','.join(patterns) if patterns else '-'} "
                        f"texts={redact(object_subtree_texts(widget))!r}"
                    )
                except Exception as e:
                    log.info(f"PROTONVPN DIAG: [{index}] unreadable: {e}")
        except Exception as e:
            log.debugWarning(f"PROTONVPN: _log_widget_diagnostics error: {e}")

    # AutomationId attendus, sondés lors du diagnostic pour savoir lesquels
    # existent réellement dans la fenêtre.
    DIAGNOSTIC_IDS = tuple(WIDGET_AUTOMATION_IDS) + (
        "ConnectionCardConnectButton",
        CHANGE_SERVER_AUTOMATION_ID,
        "ConnectionCardDisconnectButton",
        "ShowVolumeFlyoutButton",
        "ShowIpFlyoutButton",
        "ShowServerLoadFlyoutButton",
        "ShowProtocolFlyoutButton",
        KILL_SWITCH_TOGGLE_AUTOMATION_ID,
        CONTAINER_LOCATION_DETAILS,
        CONTAINER_CONNECTION_DETAILS,
        SEARCH_BOX_AUTOMATION_ID,
    )

    def _describe_object(self, obj, title):
        """Tout ce que l'add-on peut lire d'un objet, en lignes de texte.

        Sert à faire remonter un contrôle mal étiqueté : sans l'AutomationId, le
        type de contrôle et le contenu réels, il n'y a pas de correction
        possible, seulement des suppositions.
        """
        lines = [f"--- {title} ---"]

        if obj is None:
            lines.append("  (aucun objet)")
            return lines

        element = _element_of(obj)

        def add(label, value):
            lines.append(f"  {label}: {redact(value)!r}")

        control_type = element_control_type(element)
        add("automationId", get_automation_id(obj))
        add(
            "controlType",
            f"{control_type} ({CONTROL_TYPE_NAMES.get(control_type, 'inconnu')})",
        )
        add("className", _read(
            element, 'CachedClassName', 'cachedClassName',
            'CurrentClassName', 'currentClassName',
        ) or "")
        add("frameworkId", element_framework_id(element))
        add("nom brut", element_name(element))

        # Ce que l'utilisateur entend réellement, classes overlay comprises :
        # c'est la comparaison avec le nom brut qui dit si l'add-on est en cause.
        for label, getter in (
            ("nom annoncé", lambda: obj.name),
            ("description", lambda: obj.description),
            ("valeur", lambda: obj.value),
            # Le nom de l'énumération, pas sa valeur : « BUTTON » et
            # « FOCUSABLE » se lisent, « 9 » et « 16777216» non.
            ("rôle NVDA", lambda: _enum_name(obj.role)),
            ("états NVDA", lambda: sorted(_enum_name(s) for s in obj.states)),
        ):
            try:
                add(label, getter())
            except Exception as e:
                add(label, f"<illisible: {type(e).__name__}>")

        add("rect", element_rect(element))
        lines.append(
            "  classes overlay: "
            + ", ".join(cls.__name__ for cls in type(obj).__mro__[:5])
        )
        patterns = self._available_patterns(element)
        lines.append(f"  patterns: {', '.join(patterns) if patterns else '-'}")

        ancestors = list(iter_ancestor_ids(element, max_levels=8))
        lines.append(f"  ancêtres (id): {ancestors}")

        content = element_subtree_content(element)
        lines.append(f"  sous-arbre, {len(content.texts)} texte(s):")
        for index, text in enumerate(content.texts[:20]):
            lines.append(f"    [{index}] {redact(text)!r}")
        if content.nested_ids:
            lines.append(f"  lignes imbriquées: {content.nested_ids[:10]}")

        return lines

    # Patterns UIA sondés lors de l'inspection : ce qu'un contrôle sait faire
    # en dit souvent plus long que son nom. Identifiants officiels UIA_*PatternId.
    INSPECTED_PATTERNS = (
        ("Invoke", 10000),
        ("Selection", 10001),
        ("Value", 10002),
        ("ExpandCollapse", 10005),
        ("SelectionItem", 10010),
        ("Text", 10014),
        ("Toggle", 10015),
        ("ScrollItem", 10017),
        ("LegacyIAccessible", 10018),
        ("VirtualizedItem", 10020),
    )

    def _available_patterns(self, element):
        """Noms des patterns UIA réellement exposés par l'élément."""
        if element is None:
            return []

        available = []
        for name, pattern_id in self.INSPECTED_PATTERNS:
            try:
                if element.GetCurrentPattern(pattern_id):
                    available.append(name)
            except Exception:
                continue
        return available

    @script(
        # Traducteurs : description du raccourci dans Gestes de commandes.
        description=_("Inspect the focused object"),
        gesture="kb:control+shift+f10",
    )
    def script_inspectObject(self, gesture):
        """Décrit l'objet actif dans le journal et dans le presse-papiers."""
        lines = [f"PROTONVPN INSPECT: add-on v{get_addon_version()}"]

        try:
            focus = api.getFocusObject()
        except Exception as e:
            focus = None
            lines.append(f"  focus illisible: {e}")

        lines.extend(self._describe_object(focus, "objet actif (focus)"))

        # L'objet de navigation diffère dès que l'utilisateur explore à la revue
        # d'objets, et c'est souvent lui qui porte le contrôle mal étiqueté.
        try:
            navigator = api.getNavigatorObject()
        except Exception:
            navigator = None

        if navigator is not None and navigator != focus:
            lines.extend(self._describe_object(navigator, "objet de navigation"))

        report = "\n".join(lines)

        for line in lines:
            log.info(line)

        copied = False
        try:
            copied = bool(api.copyToClip(report))
        except Exception as e:
            log.debugWarning(f"PROTONVPN: cannot copy the report: {e}")

        if copied:
            ui.message(_("Object details written to the log and copied to the clipboard"))
        else:
            ui.message(_("Object details written to the NVDA log"))

    @script(
        # Traducteurs : description du raccourci dans Gestes de commandes.
        description=_("Write ProtonVPN diagnostics to the NVDA log"),
        gesture="kb:control+shift+f9",
    )
    def script_logDiagnostics(self, gesture):
        try:
            fg = api.getForegroundObject()
            root, reason = get_uia_root()
            log.info(
                f"PROTONVPN DIAG: add-on v{get_addon_version()} "
                f"foreground class={getattr(fg, 'windowClassName', None)!r} "
                f"hwnd={getattr(fg, 'windowHandle', None)} "
                f"uiaRoot={'yes' if root is not None else 'no'} ({reason})"
            )

            for automation_id in self.DIAGNOSTIC_IDS:
                elements, find_reason = self._search_elements(automation_id)
                log.info(
                    f"PROTONVPN DIAG: {automation_id}: "
                    f"{len(elements)} hit(s) ({find_reason})"
                )

            snapshot, snapshot_reason = snapshot_window_elements()
            log.info(f"PROTONVPN DIAG: snapshot {len(snapshot)} elements ({snapshot_reason})")

            edits = [
                (automation_id, redact(name))
                for automation_id, name, control_type, _rect, _el in snapshot
                if control_type == UIA_EDIT_CONTROL_TYPE
            ]
            log.info(f"PROTONVPN DIAG: {len(edits)} edit field(s): {edits[:10]}")

            # Même photographie que ci-dessus : la reprendre coûterait un second
            # aller-retour sur plusieurs centaines d'éléments pour rien.
            rows = collect_location_rows(snapshot)
            countries = [row for row in rows if row.kind == KIND_COUNTRY]
            cities = [row for row in rows if row.kind == KIND_CITY]
            log.info(
                f"PROTONVPN DIAG: {len(rows)} location row(s): "
                f"{len(countries)} country(ies), {len(cities)} city(ies)"
            )
            for row in rows[:60]:
                # Les libellés viennent de l'application : ils passent par
                # redact comme tout le reste. Une ligne dont la fenêtre de texte
                # déborde sur le panneau de connexion pourrait porter l'adresse
                # IP ou celle du compte, et ce journal part dans un rapport.
                # Le conteneur de la ligne, qui dit de quelle liste elle vient.
                # Le relevé du 21 novembre a montré trois lignes nommées en
                # clair — « Connect_to_France » — classées en villes, alors que
                # ce sont des pays : l'identifiant ne suffit donc pas toujours à
                # trancher. Savoir dans quel panneau la ligne se trouve est ce
                # qui manque pour le faire sans deviner.
                containers = [
                    automation_id
                    for automation_id in iter_ancestor_ids(row.element, 4)
                    if automation_id
                ]
                log.info(
                    f"PROTONVPN DIAG: row id={row.automation_id!r} kind={row.kind} "
                    f"label={redact(row.label)!r} "
                    f"country={redact(row.country_label)!r} "
                    f"nested={row.nested} rect={row.rect} "
                    f"containers={containers} "
                    f"announced={redact(format_location(row))!r}"
                )

            widgets = self._iter_widget_buttons()
            self._log_widget_diagnostics(widgets, "manual diagnostics")

            # Sans widget identifiable, lister les boutons de la fenêtre montre
            # comment ProtonVPN structure réellement son interface. C'est le cas
            # dès que les paramètres sont ouverts, donc souvent : le relevé est
            # donc borné, et le contenu n'est lu que pour les boutons qui n'ont
            # pas de nom — les seuls dont il apprenne quelque chose. Lire les
            # quarante sans distinction demandait dix-sept secondes.
            if not widgets:
                buttons = find_buttons()
                log.info(f"PROTONVPN DIAG: {len(buttons)} button(s) in window")
                for index, button in enumerate(buttons[:MAX_DIAGNOSTIC_BUTTONS]):
                    try:
                        name = raw_name(button)
                        texts = object_subtree_texts(button) if not name.strip() else []
                        log.info(
                            f"PROTONVPN DIAG: button[{index}] "
                            f"automationId={get_automation_id(button)!r} "
                            f"name={redact(name)!r} "
                            f"texts={redact(texts)!r}"
                        )
                    except Exception as e:
                        log.info(f"PROTONVPN DIAG: button[{index}] unreadable: {e}")
        except Exception as e:
            log.error(f"PROTONVPN: diagnostics failed: {e}")

        ui.message(_("Diagnostics written to the NVDA log"))


log.info("PROTONVPN: AppModule class defined successfully")
log.info("=" * 60)
