"""
Add-on NVDA - Module d'application ProtonVPN
Fichier: protonvpnservice.py

La version fait foi dans buildVars.py uniquement : ne pas la recopier ici.

Améliore l'accessibilité de ProtonVPN avec :
- Extraction des valeurs dynamiques via UIA (IP, Pays, Fournisseur)
- Labellisation intelligente par position/siblings
- Bouton VPN Plus promo avec texte marketing accessible
- Pas d'OCR requis - utilise uniquement l'arbre UIA

RACCOURCIS (dans ProtonVPN uniquement):
- Ctrl+Shift+D : Connecter / Déconnecter le VPN
- Ctrl+Shift+K : Activer / Désactiver le Kill Switch
- Ctrl+Shift+C : Ouvrir le sélecteur de pays
- Ctrl+Shift+T : Annoncer les informations de trafic
- Ctrl+Shift+L : Rechercher un pays
- Ctrl+Shift+F9 : Écrire un diagnostic dans le journal de NVDA
"""

# ============================================================================
# LOG IMMEDIAT AU CHARGEMENT
# ============================================================================
from logHandler import log
log.info("PROTONVPN: protonvpnservice.py loading...")

# ============================================================================
# IMPORTS
# ============================================================================
import appModuleHandler
import controlTypes
from NVDAObjects.UIA import UIA
import ui
import api
import re
import unicodedata

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
    _ = lambda x: x

# ============================================================================
# CONFIGURATION
# ============================================================================
# ============================================================================
# CONFIGURATION
# ============================================================================
DEBUG_MODE = False

# Plage Y pour détecter les boutons LocationDetailsPage (ajustable)
LOCATION_DETAILS_Y_MIN = 900
LOCATION_DETAILS_Y_MAX = 1300

# Regex pour détecter une adresse IP
IP_REGEX = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b')

# Libellés permettant d'identifier le widget Kill Switch, quelle que soit sa
# position dans la colonne (l'ordre varie selon l'offre et la version de l'app).
KILL_SWITCH_KEYWORDS = (
    "kill switch", "killswitch", "arrêt d'urgence", "coupe-circuit",
    "coupure d'urgence", "interrupteur d'arrêt",
)

# AutomationId réels des widgets de la colonne droite, relevés dans l'arbre UIA
# de ProtonVPN. Il n'existe pas d'identifiant générique « WidgetButton » :
# chaque widget porte le sien, d'où l'échec des recherches précédentes.
WIDGET_AUTOMATION_IDS = {
    "NetShieldWidgetButton": _("NetShield"),
    "KillSwitchWidgetButton": _("Kill Switch"),
    "SplitTunnelingWidgetButton": _("Split tunneling"),
    "PortForwardingWidgetButton": _("Port forwarding"),
}

KILL_SWITCH_AUTOMATION_ID = "KillSwitchWidgetButton"

# ProtonVPN expose un bouton par pays, dont l'AutomationId est préfixé
# (Connect_to_DE, Connect_to_SN, Connect_to_Fastest…) et dont le contenu porte
# le nom du pays dans la langue de l'interface.
COUNTRY_BUTTON_PREFIX = "Connect_to_"

# « Pays le plus rapide » ouvre la liste : son identifiant est exact, donc
# trouvable instantanément, ce qui donne un point d'entrée vers le conteneur.
COUNTRY_LIST_ANCHOR_ID = "Connect_to_Fastest"

# Champ de recherche de ProtonVPN. Il filtre la liste complète des pays, y
# compris ceux que l'interface n'a pas encore matérialisés : c'est la seule voie
# fiable, notre propre liste ne voyant que les pays déjà affichés.
SEARCH_BOX_AUTOMATION_ID = "SearchTextBox"

# Garde-fou sur la photographie de la fenêtre : la liste des serveurs peut
# compter des milliers d'éléments, inutile de tous les rapatrier.
MAX_SNAPSHOT_ELEMENTS = 4000

# Type de contrôle UIA d'un champ de saisie, repéré lors du diagnostic pour
# localiser le champ de recherche de ProtonVPN.
UIA_EDIT_CONTROL_TYPE = 50004

# Quand le VPN est connecté, LocationDetailsPage n'existe pas : le changement de
# serveur passe par ce bouton de la carte de connexion.
CHANGE_SERVER_AUTOMATION_ID = "ConnectionCardChangeServerButton"

# Position historique du Kill Switch dans la colonne, utilisée uniquement en
# dernier recours quand ni l'identifiant ni le libellé ne permettent de le
# reconnaître.
KILL_SWITCH_FALLBACK_INDEX = 1

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
# Recherche par sous-chaîne, réservée aux boutons de la carte de connexion.
DISCONNECT_KEYWORDS = ("disconnect", "déconnecter")
CONNECT_KEYWORDS = ("connect", "connecter")

# Second repli, hors carte de connexion : le libellé complet doit correspondre.
# « Connection details » ne vaut pas « connect », contrairement à une recherche
# par sous-chaîne qui retiendrait n'importe quel bouton contenant ce fragment.
DISCONNECT_LABELS = frozenset(("disconnect", "déconnecter", "se déconnecter"))
CONNECT_LABELS = frozenset(("connect", "connecter", "se connecter"))

# Confirmation d'état après action : une connexion ProtonVPN dépasse souvent
# une seconde et demie, il faut donc sonder plusieurs fois.
VPN_STATE_POLL_MS = 1200
VPN_STATE_MAX_ATTEMPTS = 8


def get_addon_version():
    """Retourne la version déclarée dans le manifeste de l'add-on.

    Le manifeste est généré depuis buildVars.py : c'est la seule source de vérité.
    """
    try:
        return addonHandler.getCodeAddon().manifest["version"]
    except Exception:
        # addonHandler peut être absent (import échoué) ou le module chargé
        # hors d'un add-on installé.
        return "unknown"


def redact(text):
    """Masque les adresses IP avant journalisation.

    Le journal NVDA est fréquemment joint tel quel aux rapports de bug publics :
    il ne doit jamais contenir l'IP réelle ni l'IP du tunnel.
    """
    if not text:
        return text
    return IP_REGEX.sub("[ip]", str(text))


# ============================================================================
# FONCTIONS UTILITAIRES - UIA
# ============================================================================

def _uia_attr(obj, *names):
    """Retourne le premier attribut existant parmi names.

    comtypes expose les membres COM tantôt en PascalCase, tantôt avec une
    initiale minuscule selon la génération du typelib : on accepte les deux
    plutôt que de parier sur une seule orthographe.
    """
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def get_uia_root():
    """Retourne (élément UIA racine de la fenêtre, explication).

    L'élément du premier plan n'est pas toujours un objet UIA : dans ce cas on
    passe par le handle de fenêtre. Retourner l'explication permet de la
    journaliser, faute de quoi un échec de ce chemin reste invisible.
    """
    fg = api.getForegroundObject()
    if not fg:
        return None, "no foreground object"

    element = getattr(fg, 'UIAElement', None)
    if element is not None:
        return element, "foreground UIAElement"

    try:
        import UIAHandler
        client = getattr(UIAHandler.handler, 'clientObject', None)
        hwnd = getattr(fg, 'windowHandle', None)
        from_handle = _uia_attr(client, 'ElementFromHandle', 'elementFromHandle') if client else None
        if from_handle and hwnd:
            element = from_handle(hwnd)
            if element is not None:
                return element, "ElementFromHandle"
    except Exception as e:
        return None, f"ElementFromHandle failed: {e}"

    return None, "foreground exposes no UIA element"


def find_via_uia_api(automation_id):
    """Recherche par FindAll d'UIA. Retourne (liste, explication).

    Un seul appel inter-processus, exécuté côté ProtonVPN, là où un parcours
    récursif en déclenche un par nœud de l'arbre.

    Les éléments sont récupérés avec la requête de cache de NVDA :
    NVDAObjects.UIA lit des propriétés mises en cache à la construction, et un
    élément obtenu sans cache fait échouer l'instanciation avec E_INVALIDARG.
    """
    try:
        import UIAHandler

        element, reason = get_uia_root()
        if element is None:
            return [], reason

        client = getattr(UIAHandler.handler, 'clientObject', None)
        create_condition = _uia_attr(
            client, 'CreatePropertyCondition', 'createPropertyCondition'
        ) if client else None
        if create_condition is None:
            return [], "no CreatePropertyCondition on UIA client"

        property_id = getattr(UIAHandler, 'UIA_AutomationIdPropertyId', 30011)
        scope = getattr(UIAHandler, 'TreeScope_Descendants', 4)
        condition = create_condition(property_id, automation_id)

        cache_request = getattr(UIAHandler.handler, 'baseCacheRequest', None)
        find_all_cached = _uia_attr(element, 'FindAllBuildCache', 'findAllBuildCache')

        if cache_request is not None and find_all_cached is not None:
            array = find_all_cached(scope, condition, cache_request)
            reason = f"{reason}+cache"
        else:
            find_all = _uia_attr(element, 'FindAll', 'findAll')
            if find_all is None:
                return [], "no FindAll on root element"
            array = find_all(scope, condition)

        if array is None:
            return [], f"FindAll returned nothing ({reason})"

        length = _uia_attr(array, 'Length', 'length')
        get_element = _uia_attr(array, 'GetElement', 'getElement')
        if length is None or get_element is None:
            return [], "unexpected element array interface"

        return [UIA(UIAElement=get_element(i)) for i in range(length)], reason

    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def find_by_tree_walk(automation_ids, max_depth=15):
    """Parcours récursif de secours, tous identifiants en une seule passe.

    Lent — un appel inter-processus par nœud — mais indépendant des interfaces
    UIA. Sert de filet quand la recherche rapide ne donne rien.
    """
    # Une chaîne doit être traitée comme un identifiant unique : set("Abc")
    # produirait un ensemble de caractères, qui ne correspondrait à rien.
    if isinstance(automation_ids, str):
        automation_ids = (automation_ids,)

    fg = api.getForegroundObject()
    if not fg:
        return []

    wanted = set(automation_ids)
    found = []

    def search(obj, depth=0):
        if depth > max_depth:
            return
        try:
            if get_automation_id(obj) in wanted:
                found.append(obj)
            for child in obj.children:
                search(child, depth + 1)
        except Exception:
            pass

    search(fg)
    return found


def normalize_for_search(text):
    """Minuscules sans accents, pour un filtre tolérant à la saisie.

    Permet de trouver « Algérie » en tapant « algerie ».
    """
    decomposed = unicodedata.normalize('NFD', text or "")
    stripped = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    return stripped.lower()


def collect_country_buttons(root, max_depth):
    """Boutons pays trouvés sous root, dans l'ordre de l'arbre.

    Cet ordre correspond à l'ordre affiché, « Pays le plus rapide » en tête.
    """
    entries = []
    seen = set()

    def search(obj, depth=0):
        if depth > max_depth:
            return
        try:
            automation_id = get_automation_id(obj)
            if automation_id.startswith(COUNTRY_BUTTON_PREFIX):
                if automation_id not in seen:
                    seen.add(automation_id)
                    label = get_all_descendant_names(obj, 4).strip()
                    entries.append((label or automation_id, obj))
            for child in obj.children:
                search(child, depth + 1)
        except Exception:
            pass

    search(root)
    return entries


def snapshot_window_elements():
    """Photographie la fenêtre en un seul appel : [(automationId, name, type)].

    FindAllBuildCache rapatrie toutes les propriétés voulues d'un coup. Lire
    ensuite obj.children ou obj.name élément par élément coûte un aller-retour
    inter-processus à chaque accès : c'est ce qui gelait NVDA une dizaine de
    secondes sur la liste des pays.

    Retourne (éléments, explication). Les éléments sont dans l'ordre du
    document, ce qui permet de rattacher un libellé au bouton qui le précède.
    """
    try:
        import UIAHandler

        root, reason = get_uia_root()
        if root is None:
            return [], reason

        client = getattr(UIAHandler.handler, 'clientObject', None)
        create_cache = _uia_attr(client, 'CreateCacheRequest', 'createCacheRequest') if client else None
        create_true = _uia_attr(client, 'CreateTrueCondition', 'createTrueCondition') if client else None
        find_all_cached = _uia_attr(root, 'FindAllBuildCache', 'findAllBuildCache')

        if not (create_cache and create_true and find_all_cached):
            return [], "cached search unavailable"

        cache_request = create_cache()
        add_property = _uia_attr(cache_request, 'AddProperty', 'addProperty')
        if add_property is None:
            return [], "cache request lacks AddProperty"

        for property_id in (
            getattr(UIAHandler, 'UIA_AutomationIdPropertyId', 30011),
            getattr(UIAHandler, 'UIA_NamePropertyId', 30005),
            getattr(UIAHandler, 'UIA_ControlTypePropertyId', 30003),
        ):
            add_property(property_id)

        scope = getattr(UIAHandler, 'TreeScope_Descendants', 4)
        array = find_all_cached(scope, create_true(), cache_request)
        if array is None:
            return [], "FindAllBuildCache returned nothing"

        length = _uia_attr(array, 'Length', 'length') or 0
        get_element = _uia_attr(array, 'GetElement', 'getElement')

        snapshot = []
        for index in range(min(length, MAX_SNAPSHOT_ELEMENTS)):
            element = get_element(index)
            try:
                snapshot.append((
                    _uia_attr(element, 'CachedAutomationId', 'cachedAutomationId') or "",
                    _uia_attr(element, 'CachedName', 'cachedName') or "",
                    _uia_attr(element, 'CachedControlType', 'cachedControlType') or 0,
                    element,
                ))
            except Exception:
                continue

        return snapshot, f"{reason}, {len(snapshot)} elements"

    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def pair_country_labels(snapshot):
    """Associe à chaque bouton pays le libellé qui le suit.

    FindAll rend les éléments dans l'ordre du document : un bouton
    Connect_to_XX est suivi des textes qui l'habillent, dont le nom du pays.
    On retient le premier nom non vide rencontré avant le bouton pays suivant.

    Un bouton sans libellé conserve son identifiant : mieux vaut annoncer
    « Connect_to_DE » que de faire disparaître le pays de la liste.
    """
    entries = []
    pending = None

    for automation_id, name, _control_type, element in snapshot:
        if automation_id.startswith(COUNTRY_BUTTON_PREFIX):
            if pending is not None:
                entries.append(pending)
            pending = (automation_id, element)
        elif pending is not None and name.strip():
            entries.append((name.strip(), pending[1]))
            pending = None

    if pending is not None:
        entries.append(pending)

    return entries


def find_country_buttons(max_depth=8):
    """Retourne [(libellé, cible)] des boutons de connexion par pays.

    La cible est un élément UIA brut ou un NVDAObject selon le chemin emprunté ;
    _connectToCountry accepte les deux.

    Les identifiants sont préfixés (Connect_to_DE) et non exacts : la recherche
    UIA par égalité ne s'y applique pas. On photographie donc la fenêtre en un
    appel, puis on rattache à chaque bouton le premier libellé qui le suit dans
    l'ordre du document.
    """
    snapshot, reason = snapshot_window_elements()

    if snapshot:
        entries = pair_country_labels(snapshot)
        if entries:
            return entries

    # Repli : parcours récursif, lent mais indépendant des interfaces de cache.
    log.info(f"PROTONVPN: cached country snapshot unusable ({reason}); walking tree")

    fg = api.getForegroundObject()
    return collect_country_buttons(fg, max_depth) if fg else []


def find_uia_elements(automation_ids, first_only=False):
    """Retourne les descendants portant l'un de ces AutomationId.

    Accepte une chaîne ou une suite de chaînes. Tente la recherche rapide sur
    chacune, puis retombe sur un parcours récursif unique couvrant toutes les
    valeurs — plutôt qu'un parcours par identifiant.

    Le repli est journalisé en niveau info : un échec silencieux du chemin
    rapide se traduirait par des raccourcis qui échouent instantanément, ce qui
    peut passer pour de la rapidité.
    """
    if isinstance(automation_ids, str):
        automation_ids = (automation_ids,)

    elements = []
    reasons = []
    for automation_id in automation_ids:
        found, reason = find_via_uia_api(automation_id)
        elements.extend(found)
        if not found:
            reasons.append(f"{automation_id}: {reason}")

    if not elements:
        log.info(
            f"PROTONVPN: fast UIA search found nothing ({'; '.join(reasons)}); "
            f"falling back to tree walk"
        )
        elements = find_by_tree_walk(automation_ids)

    if first_only:
        return elements[0] if elements else None
    return elements


def get_automation_id(obj):
    """Retourne l'AutomationId de l'objet."""
    try:
        return getattr(obj, 'UIAAutomationId', None) or ""
    except:
        return ""

def get_framework_id(obj):
    """Retourne le FrameworkId de l'objet."""
    try:
        if hasattr(obj, 'UIAElement') and obj.UIAElement:
            return obj.UIAElement.currentFrameworkId or ""
    except:
        pass
    return ""

def get_bounding_rect(obj):
    """Retourne le boundingRect (x1, y1, x2, y2) de l'objet."""
    try:
        if hasattr(obj, 'UIAElement') and obj.UIAElement:
            rect = obj.UIAElement.currentBoundingRectangle
            return (rect.left, rect.top, rect.right, rect.bottom)
    except:
        pass
    try:
        loc = obj.location
        if loc:
            return (loc.left, loc.top, loc.left + loc.width, loc.top + loc.height)
    except:
        pass
    return None

def get_control_type(obj):
    """Retourne le ControlType UIA de l'objet."""
    try:
        if hasattr(obj, 'UIAElement') and obj.UIAElement:
            return obj.UIAElement.currentControlType
    except:
        pass
    return None

def has_parent_with_automation_id(obj, target_id, max_levels=4):
    """Vérifie si un des parents a l'AutomationId spécifié."""
    current = obj
    for _ in range(max_levels):
        try:
            parent = current.parent
            if not parent:
                break
            parent_id = get_automation_id(parent)
            if parent_id == target_id:
                return True
            current = parent
        except:
            break
    return False

def get_parent_with_automation_id(obj, target_id, max_levels=4):
    """Retourne le parent avec l'AutomationId spécifié, ou None."""
    current = obj
    for _ in range(max_levels):
        try:
            parent = current.parent
            if not parent:
                break
            parent_id = get_automation_id(parent)
            if parent_id == target_id:
                return parent
            current = parent
        except:
            break
    return None


def has_parent_with_name_containing(obj, text_fragment, max_levels=4):
    """Vérifie si un des parents a un name contenant le texte spécifié."""
    current = obj
    for _ in range(max_levels):
        try:
            parent = current.parent
            if not parent:
                break
            parent_name = parent.name or ""
            if text_fragment.lower() in parent_name.lower():
                return True
            current = parent
        except:
            break
    return False


# ============================================================================
# DETECTION DES BOUTONS LOCATIONDETAILSPAGE
# ============================================================================

def is_location_details_dynamic_button(obj):
    """
    Détecte si l'objet est un des 3 boutons dynamiques de LocationDetailsPage.
    """
    try:
        if obj.role != controlTypes.Role.BUTTON:
            return False
        if get_framework_id(obj) != "XAML":
            return False
        if get_automation_id(obj):
            return False
        if not has_parent_with_automation_id(obj, "LocationDetailsPage", 4):
            return False
        return True
    except:
        return False


def get_location_button_index(obj):
    """Détermine l'index (0, 1, 2) du bouton dans LocationDetailsPage."""
    rect = get_bounding_rect(obj)
    if not rect:
        return -1
    
    x = rect[0]
    
    try:
        count = 0
        current = obj.previous
        while current:
            if current.role == controlTypes.Role.BUTTON:
                if not get_automation_id(current):
                    count += 1
            current = current.previous
        return count
    except:
        pass
    
    if x < 800:
        return 0
    elif x < 1200:
        return 1
    else:
        return 2


def get_location_button_label(index):
    """Retourne le label correspondant à l'index du bouton."""
    labels = {
        0: _("Your IP address"),
        1: _("Country"),
        2: _("Provider")
    }
    return labels.get(index, _("VPN information"))


# ============================================================================
# EXTRACTION DES VALEURS DYNAMIQUES VIA UIA
# ============================================================================

def get_text_descendants(obj, max_depth=5):
    """
    Récupère tous les éléments Text (ControlType=50020) descendants de l'objet.
    Retourne une liste de tuples (name, bounding_rect).
    """
    texts = []
    
    def recurse(node, depth):
        if depth > max_depth:
            return
        try:
            ct = get_control_type(node)
            if ct == 50020:  # Text
                name = node.name
                if name and name.strip():
                    rect = get_bounding_rect(node)
                    texts.append((name.strip(), rect))
            
            for child in node.children:
                recurse(child, depth + 1)
        except:
            pass
    
    try:
        for child in obj.children:
            recurse(child, 1)
    except:
        pass
    
    return texts


def get_all_text_descendants_as_string(obj, max_depth=5):
    """
    Récupère et concatène tous les textes descendants en une seule chaîne.
    """
    texts = get_text_descendants(obj, max_depth)
    if not texts:
        return ""
    return " ".join([t[0] for t in texts])


def iter_descendant_names(obj, max_depth=6):
    """Liste le nom de tous les descendants, quel que soit leur type de contrôle.

    get_text_descendants ne retient que les éléments Text (50020) ; certains
    libellés de ProtonVPN sont portés par d'autres types de contrôle et
    passaient donc inaperçus, rendant des widgets non identifiables.
    """
    names = []

    def recurse(node, depth):
        if depth > max_depth:
            return
        try:
            name = node.name
            if name and name.strip():
                names.append(name.strip())
            for child in node.children:
                recurse(child, depth + 1)
        except Exception:
            pass

    try:
        for child in obj.children:
            recurse(child, 1)
    except Exception:
        pass

    return names


def get_all_descendant_names(obj, max_depth=6):
    """Concatène le nom de tous les descendants, quel que soit leur type."""
    return " ".join(iter_descendant_names(obj, max_depth))


def get_sibling_texts(obj, direction="both", max_siblings=5):
    """Récupère les textes des éléments Text frères/voisins."""
    texts = []
    
    if direction in ("prev", "both"):
        try:
            current = obj.previous
            count = 0
            while current and count < max_siblings:
                ct = get_control_type(current)
                if ct == 50020:
                    name = current.name
                    if name and name.strip():
                        texts.append(("prev", name.strip()))
                current = current.previous
                count += 1
        except:
            pass
    
    if direction in ("next", "both"):
        try:
            current = obj.next
            count = 0
            while current and count < max_siblings:
                ct = get_control_type(current)
                if ct == 50020:
                    name = current.name
                    if name and name.strip():
                        texts.append(("next", name.strip()))
                current = current.next
                count += 1
        except:
            pass
    
    return texts


def extract_value_for_label_type(texts, label_type):
    """Extrait la valeur appropriée depuis une liste de textes selon le type de label."""
    if not texts:
        return None
    
    filtered = []
    labels_to_skip = ["votre adresse ip", "adresse ip", "ip", "pays", "fournisseur", "provider", "country"]
    
    for t in texts:
        text = t.strip() if isinstance(t, str) else t
        if not text:
            continue
        if text.lower() in labels_to_skip:
            continue
        filtered.append(text)
    
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
    
    elif label_type == "pays":
        for text in filtered:
            if len(text) <= 30 and not any(c.isdigit() for c in text):
                if text.lower() not in labels_to_skip:
                    return text
    
    elif label_type == "fournisseur":
        for text in filtered:
            if len(text) <= 50:
                if text.lower() not in labels_to_skip:
                    return text
    
    return filtered[0] if filtered else None


def extract_dynamic_value(obj, index):
    """Extrait la valeur dynamique d'un bouton LocationDetailsPage."""
    label_types = {0: "ip", 1: "pays", 2: "fournisseur"}
    label_type = label_types.get(index, "unknown")
    
    all_texts = []
    source = "none"
    
    desc_texts = get_text_descendants(obj, max_depth=5)
    if desc_texts:
        source = "descendants"
        all_texts.extend([t[0] for t in desc_texts])
    
    if not all_texts:
        sibling_texts = get_sibling_texts(obj, "both", 3)
        if sibling_texts:
            source = "siblings"
            all_texts.extend([t[1] for t in sibling_texts])
    
    if not all_texts:
        parent = get_parent_with_automation_id(obj, "LocationDetailsPage", 4)
        if parent:
            try:
                for child in parent.children:
                    ct = get_control_type(child)
                    if ct == 50020:
                        name = child.name
                        if name and name.strip():
                            all_texts.append(name.strip())
                if all_texts:
                    source = "parent_children"
            except:
                pass
    
    value = extract_value_for_label_type(all_texts, label_type)
    
    if DEBUG_MODE:
        log.debug(f"PROTONVPN: DynamicValue extraction - index={index}, labelType={label_type}, "
                  f"source={source}, texts={redact(all_texts[:5])}, value={redact(value)}")
    
    return value


# ============================================================================
# DETECTION BOUTON VPN PLUS PROMO
# ============================================================================

def is_vpn_plus_promo_button(obj):
    """
    Détecte si l'objet est le bouton VPN Plus promo.
    
    Critères STRICTS (tous requis):
    - role == BUTTON
    - FrameworkId == XAML
    - Parent chain contient "gratuit" (dans le name)
    - Descendants Text contiennent explicitement "VPN Plus"
    """
    try:
        if obj.role != controlTypes.Role.BUTTON:
            return False
        
        if get_framework_id(obj) != "XAML":
            return False
        
        # DOIT avoir un parent contenant "gratuit" - STRICTEMENT REQUIS
        if not has_parent_with_name_containing(obj, "gratuit", 6):
            return False
        
        # DOIT avoir des descendants contenant exactement "VPN Plus" - STRICTEMENT REQUIS
        texts = get_all_text_descendants_as_string(obj, 5).lower()
        if "vpn plus" not in texts:
            return False
        
        if DEBUG_MODE:
            log.info(f"PROTONVPN: VPN Plus promo button detected!")
        
        return True
    except Exception as e:
        log.error(f"PROTONVPN: is_vpn_plus_promo_button error: {e}")
        return False


def is_overlay_promo_button(obj):
    """
    Détecte si l'objet est une carte promo dans OverlayMessage.
    
    Critères:
    - FrameworkId == XAML
    - Role == BUTTON (ou role focusable/invocable)
    - Parent avec AutomationId == "OverlayMessage"
    - Au moins 2 descendants Text visibles
    - AutomationId vide (pas un bouton standard)
    """
    try:
        # Vérifier FrameworkId
        if get_framework_id(obj) != "XAML":
            return False
        
        # Vérifier rôle (bouton ou custom invocable)
        if obj.role != controlTypes.Role.BUTTON:
            return False
        
        # AutomationId doit être vide (carte custom, pas bouton standard)
        if get_automation_id(obj):
            return False
        
        # DOIT avoir un parent avec AutomationId == "OverlayMessage"
        if not has_parent_with_automation_id(obj, "OverlayMessage", 4):
            return False
        
        # Doit avoir au moins 2 descendants Text
        desc_texts = get_text_descendants(obj, max_depth=5)
        if len(desc_texts) < 2:
            return False
        
        if DEBUG_MODE:
            log.info(f"PROTONVPN: OverlayPromoButton detected! ({len(desc_texts)} text descendants)")
        
        return True
    except Exception as e:
        log.error(f"PROTONVPN: is_overlay_promo_button error: {e}")
        return False


def extract_overlay_promo_text(obj):
    """
    Extrait et formate le texte de la carte promo OverlayMessage.
    
    Retourne un texte structuré pour l'annonce NVDA.
    """
    desc_texts = get_text_descendants(obj, max_depth=5)
    
    if not desc_texts:
        return _("VPN Plus offer")
    
    # Extraire tous les textes
    all_texts = [t[0].strip() for t in desc_texts if t[0] and t[0].strip()]
    
    if not all_texts:
        return _("VPN Plus offer")
    
    # Construire un texte structuré
    # Premier texte = titre/résumé principal
    # Autres textes = détails
    
    # Joindre avec des points ou espaces
    formatted_parts = []
    for txt in all_texts:
        # Nettoyer et ajouter ponctuation si nécessaire
        txt = txt.strip()
        if txt and not txt.endswith(('.', '!', '?')):
            txt += '.'
        formatted_parts.append(txt)
    
    result = ' '.join(formatted_parts)
    
    # Préfixer avec "VPN Plus" si pas déjà présent
    if "vpn plus" not in result.lower():
        result = "VPN Plus. " + result
    
    if DEBUG_MODE:
        log.info(f"PROTONVPN: OverlayPromo text extracted: {result[:100]}...")
    
    return result



def extract_vpn_plus_long_text(obj):
    """
    Extrait le texte marketing long du bouton VPN Plus.
    Retourne un texte nettoyé et formaté.
    """
    texts = get_text_descendants(obj, max_depth=5)
    if not texts:
        return ""
    
    # Filtrer et nettoyer les textes
    all_texts = [t[0] for t in texts if t[0]]
    
    # Joindre avec des espaces et nettoyer
    full_text = " ".join(all_texts)
    
    # Nettoyer les espaces multiples
    full_text = re.sub(r'\s+', ' ', full_text).strip()
    
    # Structurer en phrases si possible
    # Ajouter des points après certains patterns
    full_text = re.sub(r'(\d+ pays)', r'\1.', full_text)
    full_text = re.sub(r'(VPN Plus)', r'\1.', full_text, count=1)
    
    if DEBUG_MODE:
        log.info(f"PROTONVPN: VPN Plus long text extracted: {full_text[:100]}...")
    
    return full_text


# ============================================================================
# DETECTION BOUTONS CONNECTIONDETAILSPAGE (VPN connecté)
# ============================================================================

def is_connection_details_dynamic_button(obj):
    """
    Détecte si l'objet est un bouton dynamique de ConnectionDetailsPage.
    
    Ces boutons apparaissent quand le VPN est connecté et affichent:
    - Adresse IP du VPN (ShowIpFlyoutButton)
    - Trafic total (ShowVolumeFlyoutButton)
    - Trafic actuel (E)
    """
    try:
        if obj.role != controlTypes.Role.BUTTON:
            return False
        
        if get_framework_id(obj) != "XAML":
            return False
        
        # Vérifier si parent contient ConnectionDetailsPage
        if has_parent_with_automation_id(obj, "ConnectionDetailsPage", 4):
            return True
        
        return False
    except Exception as e:
        log.error(f"PROTONVPN: is_connection_details_dynamic_button error: {e}")
        return False


def extract_connection_details_label_and_values(obj):
    """
    Extrait le label et les valeurs d'un bouton ConnectionDetailsPage.
    
    Retourne (label, values_list) :
    - label = premier texte descriptif (ex: "Adresse IP du VPN", "Trafic total")
    - values_list = liste des valeurs dynamiques (ex: ["37.19.199.137"] ou ["416 o/s", "0 o/s"])
    """
    desc_texts = get_text_descendants(obj, max_depth=5)
    
    if not desc_texts:
        # Fallback: utiliser le nom de l'objet et l'AutomationId
        automationId = get_automation_id(obj)
        original_name = obj.name or ""
        
        label_mapping = {
            "ShowIpFlyoutButton": _("VPN IP address"),
            "ShowVolumeFlyoutButton": _("Total traffic"),
            "E": _("Current traffic (KB/s)"),
        }
        label = label_mapping.get(automationId, _("VPN info"))
        values = [original_name] if original_name else []
        return label, values
    
    # Extraire tous les textes
    all_texts = [t[0] for t in desc_texts if t[0]]
    
    if not all_texts:
        return _("VPN info"), []
    
    # Le premier texte est généralement le label
    # Les suivants sont les valeurs
    label = all_texts[0]
    values = all_texts[1:] if len(all_texts) > 1 else []
    
    # Heuristiques pour identifier le label vs les valeurs
    # Les labels contiennent généralement des mots comme "Adresse", "Trafic", "IP", etc.
    label_keywords = ["adresse", "ip", "trafic", "volume", "actuel", "total", "ko/s", "o/s"]
    
    # Vérifier si le premier élément ressemble vraiment à un label
    first_lower = all_texts[0].lower()
    is_first_a_label = any(kw in first_lower for kw in label_keywords)
    
    if not is_first_a_label and len(all_texts) > 1:
        # Le premier n'est pas un label, c'est peut-être une valeur
        # Chercher un vrai label dans les textes suivants
        for i, txt in enumerate(all_texts[1:], 1):
            if any(kw in txt.lower() for kw in label_keywords):
                # Trouvé un label, réorganiser
                label = txt
                values = all_texts[:i] + all_texts[i+1:]
                break
    
    if DEBUG_MODE:
        log.debug(f"PROTONVPN: ConnectionDetails extraction - label='{label}', values={redact(values)}")
    
    return label, values


# ============================================================================
# WIDGETS COLONNE DROITE
# ============================================================================

def get_widget_identity_text(obj):
    """Rassemble tout ce qui peut identifier un widget.

    Nom, description, AutomationId et noms des descendants : ProtonVPN n'expose
    pas ces libellés de façon uniforme, et se limiter aux éléments Text laissait
    certains widgets non identifiables.

    À ne pas appeler depuis _get_name : lire obj.name y relancerait _get_name.
    """
    parts = []

    for getter in (
        lambda: obj.name,
        lambda: obj.description,
        lambda: get_automation_id(obj),
    ):
        try:
            value = getter()
            if value:
                parts.append(str(value))
        except Exception:
            pass

    try:
        parts.append(get_all_descendant_names(obj, 6))
    except Exception:
        pass

    return " ".join(p for p in parts if p)


def widget_matches_keywords(obj, keywords):
    """Vérifie qu'un widget porte bien l'un des libellés attendus.

    Sert à identifier un widget par ce qu'il expose plutôt que par son rang :
    l'ordre de la colonne varie selon l'offre et la version de ProtonVPN.
    """
    try:
        haystack = get_widget_identity_text(obj).lower()
        return any(kw in haystack for kw in keywords)
    except Exception as e:
        log.debugWarning(f"PROTONVPN: widget_matches_keywords error: {e}")
        return False


def match_widget_label(text):
    """Retourne le libellé du widget correspondant au texte affiché, ou None.

    Prend le texte en paramètre plutôt que l'objet : appelée depuis _get_name,
    lire obj.name relancerait _get_name et boucherait indéfiniment.
    """
    haystack = (text or "").lower()
    for keywords, label in WIDGET_DEFINITIONS:
        if any(kw in haystack for kw in keywords):
            return label
    return None


def is_connection_card_element(obj, max_levels=6):
    """Vérifie que l'objet appartient à la carte de connexion.

    Sans cette restriction, une recherche par libellé retiendrait n'importe quel
    bouton de la fenêtre contenant « connect » — « Connection details »,
    « Reconnect » — et l'add-on invoquerait le mauvais contrôle.
    """
    current = obj
    for _level in range(max_levels):
        try:
            if get_automation_id(current).startswith("ConnectionCard"):
                return True
            current = current.parent
            if not current:
                break
        except Exception:
            break
    return False


def label_equals_any(obj, labels):
    """Vérifie que le libellé complet de l'objet est exactement l'un des libellés."""
    try:
        label = (obj.name or "").strip().lower()
        if not label:
            label = get_all_text_descendants_as_string(obj, 3).strip().lower()
        return label in labels
    except Exception:
        return False


def get_widget_state(obj):
    """Lit l'état on/off affiché par un widget.

    Retourne True (activé), False (désactivé), ou None si l'état n'est pas lisible.
    """
    try:
        for text in iter_descendant_names(obj, max_depth=6):
            normalized = text.strip().lower().rstrip('.')
            if normalized in WIDGET_STATE_ON:
                return True
            if normalized in WIDGET_STATE_OFF:
                return False
    except Exception as e:
        log.debugWarning(f"PROTONVPN: get_widget_state error: {e}")
    return None


# ============================================================================
# FONCTIONS DEBUG
# ============================================================================

# ============================================================================
# CLASSES OVERLAY
# ============================================================================

class ProtonVPNConnectButton(UIA):
    """Overlay pour le bouton principal Connecter/Déconnecter."""

    def _get_name(self):
        original_name = super().name or ""
        automationId = get_automation_id(self)

        if "disconnect" in original_name.lower() or "déconnect" in original_name.lower():
            return _("Disconnect VPN")
        if "connect" in original_name.lower():
            return _("Connect VPN")
        if automationId == "ConnectionCardConnectButton":
            return _("Connect VPN")

        return original_name or _("VPN connection button")


class ProtonVPNLocationDetailsButton(UIA):
    """Overlay pour les 3 boutons dynamiques de LocationDetailsPage."""

    def _get_name(self):
        index = get_location_button_index(self)
        label = get_location_button_label(index)
        value = extract_dynamic_value(self, index)
        
        if value:
            result = f"{label} : {value}"
        else:
            result = label
        
        if DEBUG_MODE:
            log.debug(f"PROTONVPN: LocationDetailsButton.name → \"{redact(result)}\" (index={index})")
        
        return result


class ProtonVPNConnectionDetailsButton(UIA):
    """
    Overlay pour les boutons dynamiques de ConnectionDetailsPage.
    
    Annonce: "Label : Valeur(s)" (ex: "Adresse IP du VPN : 37.19.199.137")
    """

    def _get_name(self):
        automationId = get_automation_id(self)
        label, values = extract_connection_details_label_and_values(self)
        
        if values:
            values_str = ", ".join(values)
            result = f"{label} : {values_str}"
        else:
            result = label
        
        if DEBUG_MODE:
            log.debug(f"PROTONVPN: ConnectionDetailsButton.name → \"{redact(result)}\" (ID={automationId})")
        
        return result


class ProtonVPNOverlayPromoButton(UIA):
    """
    Overlay pour la carte promo dans OverlayMessage.
    
    Construit dynamiquement un label à partir des descendants Text.
    """

    def _get_name(self):
        promo_text = extract_overlay_promo_text(self)
        
        if DEBUG_MODE:
            log.info(f"PROTONVPN: OverlayPromoButton.name → \"{promo_text[:60]}...\"")
        
        return promo_text


class ProtonVPNPlusPromoButton(UIA):
    """
    Overlay pour le bouton VPN Plus promo.
    
    - name = "Passer à VPN Plus" (court, pour le focus)
    - description = texte marketing long (accessible via NVDA+Tab)
    """

    def _get_name(self):
        return _("Upgrade to VPN Plus")

    def _get_description(self):
        """Retourne le texte marketing long pour NVDA+Tab."""
        long_text = extract_vpn_plus_long_text(self)

        if DEBUG_MODE:
            log.info(f"PROTONVPN: VPNPlusPromoButton.description → \"{long_text[:80]}...\"")
        
        return long_text


class ProtonVPNWidgetButton(UIA):
    """Overlay pour les widgets colonne droite (NetShield, Kill Switch, etc.).

    Le libellé et l'état sont lus dans ce que le widget affiche. Aucune
    déduction par position : l'ordre de la colonne dépend de l'offre et de la
    version, et une étiquette fausse est plus dangereuse qu'une étiquette
    absente puisqu'elle inspire confiance.
    """

    def _get_widgetState(self):
        """État on/off du widget. NVDA met la valeur en cache pour le cycle."""
        return get_widget_state(self)

    def _get_name(self):
        # L'AutomationId identifie le widget sans ambiguïté.
        label = WIDGET_AUTOMATION_IDS.get(get_automation_id(self))

        if label is None:
            # super().name et non self.name : lire self.name relancerait _get_name.
            original_name = super().name or ""
            displayed = original_name + " " + get_all_descendant_names(self, 6)
            label = match_widget_label(displayed)

            if label is None:
                # Widget non reconnu : conserver ce que fournit l'application.
                label = original_name.strip() or _("ProtonVPN button")

        if DEBUG_MODE:
            log.debug(f"PROTONVPN: WidgetButton.name → \"{label}\"")

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


class ProtonVPNSideWidgetButton(UIA):
    """Overlay pour les widgets avec AutomationId spécifique."""

    AUTOMATION_ID_MAPPING = {
        "PortForwardingWidgetButton": _("Port forwarding"),
        "SettingsButton": _("Settings"),
        "TitleBarMenuButton": _("Main menu"),
    }

    def _get_name(self):
        original_name = super().name or ""
        automationId = get_automation_id(self)

        if original_name.strip():
            return original_name

        if automationId in self.AUTOMATION_ID_MAPPING:
            return self.AUTOMATION_ID_MAPPING[automationId]

        if automationId:
            return _("Button {}").format(automationId)

        return _("ProtonVPN button")


class ProtonVPNGenericButton(UIA):
    """Overlay générique pour les boutons sans nom (fallback)."""

    def _get_name(self):
        original_name = super().name or ""

        if original_name and len(original_name.strip()) > 2:
            return original_name

        # Un bouton sans nom porte souvent son libellé dans son contenu : les
        # boutons pays de ProtonVPN affichent ainsi « Allemagne », « Sénégal ».
        # Annoncer l'AutomationId à la place rendait la liste des pays
        # inutilisable — « Bouton (Connect_to_DE) » n'apprend rien.
        displayed = get_all_descendant_names(self, 4).strip()
        if displayed:
            return displayed

        automationId = get_automation_id(self)
        if automationId:
            return _("Button ({})").format(automationId)

        return _("Unnamed button")


# ============================================================================
# DIALOGUE DE SELECTION DE PAYS
# ============================================================================

if GUI_AVAILABLE:

    class CountrySelectionDialog(wx.Dialog):
        """Liste des pays avec champ de recherche.

        Évite de parcourir plusieurs dizaines de boutons à la flèche : on tape
        quelques lettres et on valide.
        """

        def __init__(self, parent, entries, on_select):
            super().__init__(parent, title=_("Connect to a country"))

            self._entries = entries
            self._filtered = list(entries)
            self._on_select = on_select

            mainSizer = wx.BoxSizer(wx.VERTICAL)

            mainSizer.Add(
                wx.StaticText(self, label=_("&Filter:")),
                flag=wx.ALL, border=5,
            )
            self._filterCtrl = wx.TextCtrl(self)
            mainSizer.Add(self._filterCtrl, flag=wx.EXPAND | wx.ALL, border=5)

            mainSizer.Add(
                wx.StaticText(self, label=_("Cou&ntries:")),
                flag=wx.ALL, border=5,
            )
            self._listBox = wx.ListBox(self, style=wx.LB_SINGLE, size=(320, 260))
            mainSizer.Add(self._listBox, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

            buttonSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
            if buttonSizer:
                mainSizer.Add(buttonSizer, flag=wx.EXPAND | wx.ALL, border=5)

            self.SetSizerAndFit(mainSizer)

            self._filterCtrl.Bind(wx.EVT_TEXT, self._onFilterChanged)
            self._listBox.Bind(wx.EVT_LISTBOX_DCLICK, self._onOk)
            self.Bind(wx.EVT_BUTTON, self._onOk, id=wx.ID_OK)

            self._refreshList()
            self._filterCtrl.SetFocus()

        def _refreshList(self):
            self._listBox.Set([label for label, _obj in self._filtered])
            if self._filtered:
                self._listBox.SetSelection(0)

        def _onFilterChanged(self, event):
            needle = normalize_for_search(self._filterCtrl.GetValue())
            self._filtered = [
                entry for entry in self._entries
                if needle in normalize_for_search(entry[0])
            ]
            self._refreshList()

        def _onOk(self, event):
            index = self._listBox.GetSelection()
            if index == wx.NOT_FOUND or index >= len(self._filtered):
                wx.Bell()
                return

            label, obj = self._filtered[index]
            callback = self._on_select
            self.Destroy()

            # Activer après fermeture : le focus doit être revenu à ProtonVPN
            # pour que l'activation aboutisse.
            wx.CallLater(100, callback, label, obj)


# ============================================================================
# CLASSE APPMODULE
# ============================================================================
log.info("PROTONVPN: Defining AppModule class...")


class AppModule(appModuleHandler.AppModule):
    """Module d'application NVDA pour ProtonVPN."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        log.info(f"PROTONVPN: AppModule v{get_addon_version()} loaded (DEBUG_MODE={DEBUG_MODE})")
        if DEBUG_MODE:
            ui.message(_("ProtonVPN add-on active"))

    def chooseNVDAObjectOverlayClasses(self, obj, clsList):
        """Choisit les classes overlay appropriées."""
        try:
            role = obj.role
            name = obj.name or ""
            automationId = get_automation_id(obj)
            frameworkId = get_framework_id(obj)
            
            if role == controlTypes.Role.BUTTON and frameworkId == "XAML":
                
                # 1) Bouton principal de connexion
                if automationId == "ConnectionCardConnectButton":
                    clsList.insert(0, ProtonVPNConnectButton)
                
                # 2) Bouton VPN Plus Promo
                elif is_vpn_plus_promo_button(obj):
                    clsList.insert(0, ProtonVPNPlusPromoButton)
                    if DEBUG_MODE:
                        log.debug("PROTONVPN: → ProtonVPNPlusPromoButton")
                
                # 3) Carte promo OverlayMessage
                elif is_overlay_promo_button(obj):
                    clsList.insert(0, ProtonVPNOverlayPromoButton)
                    if DEBUG_MODE:
                        log.debug("PROTONVPN: → ProtonVPNOverlayPromoButton")
                
                # 4) Boutons ConnectionDetailsPage (IP VPN, Trafic - VPN connecté)
                elif is_connection_details_dynamic_button(obj):
                    clsList.insert(0, ProtonVPNConnectionDetailsButton)
                    if DEBUG_MODE:
                        log.debug("PROTONVPN: → ProtonVPNConnectionDetailsButton")
                
                # 4) Boutons LocationDetailsPage (IP/Pays/Fournisseur)
                elif is_location_details_dynamic_button(obj):
                    clsList.insert(0, ProtonVPNLocationDetailsButton)
                    if DEBUG_MODE:
                        log.debug("PROTONVPN: → ProtonVPNLocationDetailsButton")
                
                # 5) Widgets de la colonne droite (NetShield, Kill Switch, etc.)
                elif automationId in WIDGET_AUTOMATION_IDS:
                    clsList.insert(0, ProtonVPNWidgetButton)

                # 6) Autres boutons à AutomationId connu
                elif automationId in ("SettingsButton", "TitleBarMenuButton"):
                    clsList.insert(0, ProtonVPNSideWidgetButton)
                
                # 6) Fallback
                elif not name or len(name.strip()) <= 2:
                    clsList.insert(0, ProtonVPNGenericButton)

        except Exception as e:
            log.error(f"PROTONVPN: chooseNVDAObjectOverlayClasses error: {e}")

        super().chooseNVDAObjectOverlayClasses(obj, clsList)

    # ========================================================================
    # SCRIPTS - ACTIONS VPN
    # ========================================================================
    
    def _find_element_by_automation_id(self, target_id):
        """Recherche un élément par AutomationId. Retourne l'objet NVDA ou None."""
        return find_uia_elements(target_id, first_only=True)

    def _invoke_via_pattern(self, obj, pattern_id_name, interface_name, method_name):
        """Déclenche un élément via un pattern UIA. Retourne True en cas de succès."""
        try:
            element = getattr(obj, 'UIAElement', None)
            if not element:
                return False

            import UIAHandler
            pattern_id = getattr(UIAHandler, pattern_id_name, None)
            interface = getattr(UIAHandler, interface_name, None)
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

        try:
            from keyboardHandler import KeyboardInputGesture
            KeyboardInputGesture.fromName("enter").send()
            return True
        except Exception as e:
            log.error(f"PROTONVPN: keyboard fallback failed: {e}")
            return False

    def _invoke_element(self, obj):
        """Déclenche un élément, du moyen le plus fiable au moins fiable."""
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


    def _iter_buttons(self, max_depth=15):
        """Énumère les boutons de la fenêtre au premier plan."""
        buttons = []
        fg = api.getForegroundObject()
        if not fg:
            return buttons

        def search(obj, depth=0):
            if depth > max_depth:
                return
            try:
                if obj.role == controlTypes.Role.BUTTON:
                    buttons.append(obj)
                for child in obj.children:
                    search(child, depth + 1)
            except Exception:
                pass

        search(fg)
        return buttons

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
        buttons = self._iter_buttons()

        card = [b for b in buttons if is_connection_card_element(b)]
        for obj in card:
            if widget_matches_keywords(obj, DISCONNECT_KEYWORDS):
                return obj, True
        for obj in card:
            if widget_matches_keywords(obj, CONNECT_KEYWORDS):
                return obj, False

        for obj in buttons:
            if label_equals_any(obj, DISCONNECT_LABELS):
                return obj, True
        for obj in buttons:
            if label_equals_any(obj, CONNECT_LABELS):
                return obj, False

        if DEBUG_MODE:
            labels = [redact((b.name or "").strip()) for b in buttons if (b.name or "").strip()]
            log.debug(f"PROTONVPN: no connection button matched. Buttons: {labels}")

        return None

    def _connection_state(self):
        """État du VPN : True connecté, False déconnecté, None indéterminé.

        Déduit du bouton présent sur la carte de connexion.
        """
        if self._find_element_by_automation_id("ConnectionCardDisconnectButton"):
            return True
        if self._find_element_by_automation_id("ConnectionCardConnectButton"):
            return False
        return None

    def script_toggleVPN(self, gesture):
        """Connecter ou déconnecter le VPN."""
        log.debug("PROTONVPN: script_toggleVPN triggered")
        
        # Chercher d'abord le bouton Déconnecter (si VPN connecté)
        btn = self._find_element_by_automation_id("ConnectionCardDisconnectButton")
        is_disconnecting = True
        
        if not btn:
            # Sinon chercher le bouton Connecter (VPN déconnecté)
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
        
        # Annoncer immédiatement l'action
        if is_disconnecting:
            ui.message(_("Disconnecting"))
            log.debug("PROTONVPN: Disconnecting VPN")
        else:
            ui.message(_("Connecting"))
            log.debug("PROTONVPN: Connecting VPN")

        # Le bouton trouvé indique l'état de départ : Déconnecter n'est présent
        # que si le VPN est connecté. Évite un parcours d'arbre supplémentaire.
        previous_state = is_disconnecting

        # Invoquer le bouton
        if self._invoke_element(btn):
            log.debug("PROTONVPN: Button invoked successfully")
            # Lancer la confirmation d'état en différé
            try:
                import wx
                wx.CallLater(VPN_STATE_POLL_MS, self._confirm_vpn_state, previous_state)
            except:
                # Si wx n'est pas dispo, ignorer la confirmation
                pass
        else:
            ui.message(_("Action unavailable"))
    
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

            import wx
            wx.CallLater(
                VPN_STATE_POLL_MS, self._confirm_vpn_state, previous_state, attempt + 1
            )
        except Exception as e:
            log.error(f"PROTONVPN: _confirm_vpn_state error: {e}")
    
    script_toggleVPN.__doc__ = _("Toggle VPN connection")
    script_toggleVPN.category = "ProtonVPN"
    
    def _iter_widget_buttons(self):
        """Énumère les widgets de la colonne droite."""
        return find_uia_elements(tuple(WIDGET_AUTOMATION_IDS))

    def _find_widget_by_keywords(self, keywords):
        """Retourne le widget portant l'un des libellés donnés, ou None.

        L'identification repose sur le texte affiché, pas sur le rang du widget.
        """
        for widget in self._iter_widget_buttons():
            if widget_matches_keywords(widget, keywords):
                return widget
        return None

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
                    log.info(
                        f"PROTONVPN DIAG: [{index}] "
                        f"automationId={get_automation_id(widget)!r} "
                        f"name={redact(getattr(widget, 'name', '') or '')!r} "
                        f"description={redact(getattr(widget, 'description', '') or '')!r} "
                        f"descendants={redact(get_all_descendant_names(widget, 6))!r}"
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
        "LocationDetailsPage",
        "ConnectionDetailsPage",
        SEARCH_BOX_AUTOMATION_ID,
    )

    def script_logDiagnostics(self, gesture):
        """Écrit dans le journal ce que ProtonVPN expose, pour diagnostic."""
        try:
            fg = api.getForegroundObject()
            root, reason = get_uia_root()
            log.info(
                f"PROTONVPN DIAG: foreground class="
                f"{getattr(fg, 'windowClassName', None)!r} "
                f"hwnd={getattr(fg, 'windowHandle', None)} "
                f"uiaRoot={'yes' if root is not None else 'no'} ({reason})"
            )

            # Comparer les deux méthodes de recherche sur chaque identifiant
            # départage un problème d'API UIA d'un identifiant qui n'existe pas.
            for automation_id in self.DIAGNOSTIC_IDS:
                api_hits, api_reason = find_via_uia_api(automation_id)
                walk_hits = find_by_tree_walk(automation_id)
                log.info(
                    f"PROTONVPN DIAG: {automation_id}: "
                    f"uiaApi={len(api_hits)} ({api_reason}), "
                    f"treeWalk={len(walk_hits)}"
                )

            # Le nombre de pays révèle si la liste est virtualisée : très en
            # dessous de la soixantaine attendue, seuls les pays affichés
            # existent dans l'arbre et la recherche serait incomplète.
            # Champs de saisie : le champ de recherche de ProtonVPN permettrait
            # d'atteindre les pays absents de l'arbre (liste virtualisée).
            snapshot, snapshot_reason = snapshot_window_elements()
            log.info(f"PROTONVPN DIAG: snapshot {len(snapshot)} elements ({snapshot_reason})")
            edits = [
                (automation_id, redact(name))
                for automation_id, name, control_type, _el in snapshot
                if control_type == UIA_EDIT_CONTROL_TYPE
            ]
            log.info(f"PROTONVPN DIAG: {len(edits)} edit field(s): {edits[:10]}")

            countries = find_country_buttons()
            log.info(f"PROTONVPN DIAG: {len(countries)} country button(s) found")
            if countries:
                labels = [label for label, _obj in countries]
                # Le dernier pays de la liste tranche la question : s'il s'arrête
                # au milieu de l'alphabet, seuls les pays affichés existent dans
                # l'arbre et la recherche est incomplète.
                log.info(f"PROTONVPN DIAG: first countries: {labels[:5]}")
                log.info(f"PROTONVPN DIAG: last countries: {labels[-5:]}")

            widgets = self._iter_widget_buttons()
            self._log_widget_diagnostics(widgets, "manual diagnostics")

            # Sans widget identifiable, lister les boutons de la fenêtre montre
            # comment ProtonVPN structure réellement son interface.
            if not widgets:
                buttons = self._iter_buttons()
                log.info(f"PROTONVPN DIAG: {len(buttons)} button(s) in window")
                for index, button in enumerate(buttons[:40]):
                    try:
                        log.info(
                            f"PROTONVPN DIAG: button[{index}] "
                            f"automationId={get_automation_id(button)!r} "
                            f"name={redact(getattr(button, 'name', '') or '')!r} "
                            f"descendants={redact(get_all_descendant_names(button, 4))[:120]!r}"
                        )
                    except Exception as e:
                        log.info(f"PROTONVPN DIAG: button[{index}] unreadable: {e}")
        except Exception as e:
            log.error(f"PROTONVPN: diagnostics failed: {e}")

        ui.message(_("Diagnostics written to the NVDA log"))

    script_logDiagnostics.__doc__ = _("Write ProtonVPN diagnostics to the NVDA log")
    script_logDiagnostics.category = "ProtonVPN"

    def _announce_widget_state(self, keywords, label):
        """Relit et annonce l'état d'un widget après basculement."""
        try:
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

    def script_toggleKillSwitch(self, gesture):
        """Activer ou désactiver le Kill Switch."""
        log.debug("PROTONVPN: script_toggleKillSwitch triggered")

        try:
            # Identifiant exact d'abord : sans ambiguïté et sans heuristique.
            widget = find_uia_elements(KILL_SWITCH_AUTOMATION_ID, first_only=True)

            if widget is None:
                widget = self._find_widget_by_keywords(KILL_SWITCH_KEYWORDS)

            identified = widget is not None

            if not identified:
                # Aucun libellé exploitable : consigner ce que les widgets
                # exposent réellement, pour pouvoir corriger l'identification.
                widgets = self._iter_widget_buttons()
                self._log_widget_diagnostics(widgets, "Kill Switch not identified")

                # Puis retomber sur la position historique. Le widget ouvre un
                # panneau, il ne bascule pas le réglage directement : si la
                # position est mauvaise, l'utilisateur entend le panneau
                # s'ouvrir et peut le refermer, sans qu'aucun réglage n'ait été
                # modifié à son insu.
                if len(widgets) > KILL_SWITCH_FALLBACK_INDEX:
                    widget = widgets[KILL_SWITCH_FALLBACK_INDEX]

            if not widget:
                ui.message(_("Kill Switch not found"))
                return

            if not self._invoke_element(widget):
                ui.message(_("Action unavailable"))
                return

            if not identified:
                # Position supposée : annoncer sans prétendre avoir vérifié.
                ui.message(_("Kill Switch"))
                return

            # L'état résultant est relu dans l'interface : ne jamais annoncer
            # un basculement qui n'a pas été constaté.
            try:
                import wx
                wx.CallLater(
                    800,
                    self._announce_widget_state,
                    KILL_SWITCH_KEYWORDS,
                    _("Kill Switch"),
                )
            except Exception:
                ui.message(_("Kill Switch"))
        except Exception as e:
            log.error(f"PROTONVPN: script_toggleKillSwitch error: {e}")
            ui.message(_("Action unavailable"))

    script_toggleKillSwitch.__doc__ = _("Toggle Kill Switch")
    script_toggleKillSwitch.category = "ProtonVPN"
    
    def _find_location_buttons(self, max_depth=4):
        """Boutons dynamiques de LocationDetailsPage (IP, Pays, Fournisseur).

        La page est localisée par AutomationId, puis seul son sous-arbre est
        parcouru : ces boutons n'ont pas d'AutomationId propre, mais explorer
        une page coûte infiniment moins que toute la fenêtre.
        """
        page = self._find_element_by_automation_id("LocationDetailsPage")
        if not page:
            return []

        buttons = []

        def search(obj, depth=0):
            if depth > max_depth:
                return
            try:
                if obj.role == controlTypes.Role.BUTTON and not get_automation_id(obj):
                    buttons.append(obj)
                for child in obj.children:
                    search(child, depth + 1)
            except Exception:
                pass

        search(page)
        return buttons

    def script_openCountrySelector(self, gesture):
        """Ouvrir le sélecteur de pays."""
        log.debug("PROTONVPN: script_openCountrySelector triggered")

        try:
            location_btns = self._find_location_buttons()

            # Le bouton Pays est le 2ème (index 1)
            country_btn = location_btns[1] if len(location_btns) >= 2 else None

            if country_btn is None:
                # VPN connecté : LocationDetailsPage n'existe pas, le changement
                # de serveur passe par la carte de connexion.
                country_btn = find_uia_elements(
                    CHANGE_SERVER_AUTOMATION_ID, first_only=True
                )

            if country_btn is None:
                ui.message(_("Country selector not found"))
                return

            ui.message(_("Country selector"))
            if self._invoke_element(country_btn):
                log.debug("PROTONVPN: Country selector opened")
            else:
                ui.message(_("Action unavailable"))
        except Exception as e:
            log.error(f"PROTONVPN: script_openCountrySelector error: {e}")
            ui.message(_("Action unavailable"))
    
    script_openCountrySelector.__doc__ = _("Open country selector")
    script_openCountrySelector.category = "ProtonVPN"

    def script_connectToCountry(self, gesture):
        """Rechercher un pays."""
        log.debug("PROTONVPN: script_connectToCountry triggered")

        # Voie principale : le champ de recherche de ProtonVPN, qui filtre la
        # liste complète. Notre propre liste ne contient que les pays déjà
        # matérialisés par l'interface — une quarantaine sur près de cent — et
        # ne sert donc que de repli.
        search_box = find_uia_elements(SEARCH_BOX_AUTOMATION_ID, first_only=True)
        if search_box is not None:
            try:
                search_box.setFocus()
                ui.message(_("Country search"))
                return
            except Exception as e:
                log.debugWarning(f"PROTONVPN: cannot focus the search box: {e}")

        if not GUI_AVAILABLE:
            ui.message(_("Action unavailable"))
            return

        entries = find_country_buttons()
        log.debug(f"PROTONVPN: {len(entries)} country button(s) found")

        if not entries:
            ui.message(_("Country list unavailable"))
            return

        wx.CallAfter(self._showCountryDialog, entries)

    def _showCountryDialog(self, entries):
        """Affiche le dialogue de sélection sur le thread principal de NVDA."""
        try:
            gui.mainFrame.prePopup()
            try:
                dialog = CountrySelectionDialog(
                    gui.mainFrame, entries, self._connectToCountry
                )
                dialog.Show()
            finally:
                gui.mainFrame.postPopup()
        except Exception as e:
            log.error(f"PROTONVPN: country dialog failed: {e}")
            ui.message(_("Action unavailable"))

    def _connectToCountry(self, label, target):
        """Active le bouton du pays choisi.

        La cible est soit un NVDAObject, soit un élément UIA brut issu de la
        photographie : on n'en construit un objet NVDA que pour celui-là.
        """
        try:
            obj = target if hasattr(target, 'UIAElement') else UIA(UIAElement=target)
        except Exception as e:
            log.error(f"PROTONVPN: cannot wrap country element: {e}")
            ui.message(_("Action unavailable"))
            return

        ui.message(_("Connecting to {country}").format(country=label))
        if not self._invoke_element(obj):
            ui.message(_("Action unavailable"))

    script_connectToCountry.__doc__ = _("Search for a country")
    script_connectToCountry.category = "ProtonVPN"
    
    def script_announceTraffic(self, gesture):
        """Annoncer les informations de trafic."""
        log.debug("PROTONVPN: script_announceTraffic triggered")
        
        try:
            traffic_info = []

            # Recherche ciblée par AutomationId : ShowVolumeFlyoutButton porte le
            # trafic total, E le trafic courant. Interroger ces deux identifiants
            # évite de parcourir tout l'arbre pour ne garder que deux éléments.
            for automation_id in ("ShowVolumeFlyoutButton", "E"):
                for obj in find_uia_elements(automation_id):
                    label, values = extract_connection_details_label_and_values(obj)
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
    
    script_announceTraffic.__doc__ = _("Announce traffic information")
    script_announceTraffic.category = "ProtonVPN"

    # ========================================================================
    # RACCOURCIS
    # ========================================================================
    __gestures = {
        "kb:control+shift+d": "toggleVPN",
        "kb:control+shift+k": "toggleKillSwitch",
        "kb:control+shift+c": "openCountrySelector",
        "kb:control+shift+t": "announceTraffic",
        "kb:control+shift+l": "connectToCountry",
        "kb:control+shift+f9": "logDiagnostics",
    }


log.info("PROTONVPN: AppModule class defined successfully")
log.info("=" * 60)

