"""
Add-on NVDA - Module d'application ProtonVPN
Fichier: protonvpnservice.py
Version: 1.0.0

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
"""

# ============================================================================
# LOG IMMEDIAT AU CHARGEMENT
# ============================================================================
from logHandler import log
log.info("=" * 60)
log.info("PROTONVPN: protonvpnservice.py v1.0.0 loading...")
log.info("=" * 60)

# ============================================================================
# IMPORTS
# ============================================================================
import appModuleHandler
import controlTypes
from NVDAObjects.UIA import UIA
import ui
import api
import os
import re

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


# ============================================================================
# FONCTIONS UTILITAIRES - UIA
# ============================================================================

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
        log.info(f"PROTONVPN: DynamicValue extraction - index={index}, labelType={label_type}, "
                 f"source={source}, texts={all_texts[:5]}, value={value}")
    
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
        log.info(f"PROTONVPN: ConnectionDetails extraction - label='{label}', values={values}")
    
    return label, values


# ============================================================================
# WIDGETS COLONNE DROITE
# ============================================================================

def count_same_type_siblings_before(obj):
    """Compte les frères de même type avant cet objet."""
    count = 0
    try:
        current = obj.previous
        while current:
            if current.role == obj.role:
                count += 1
            current = current.previous
    except:
        pass
    return count


# ============================================================================
# FONCTIONS DEBUG
# ============================================================================

# ============================================================================
# CLASSES OVERLAY
# ============================================================================

class ProtonVPNConnectButton(UIA):
    """Overlay pour le bouton principal Connecter/Déconnecter."""

    @property
    def name(self):
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

    @property
    def name(self):
        index = get_location_button_index(self)
        label = get_location_button_label(index)
        value = extract_dynamic_value(self, index)
        
        if value:
            result = f"{label} : {value}"
        else:
            result = label
        
        if DEBUG_MODE:
            log.info(f"PROTONVPN: LocationDetailsButton.name → \"{result}\" (index={index})")
        
        return result


class ProtonVPNConnectionDetailsButton(UIA):
    """
    Overlay pour les boutons dynamiques de ConnectionDetailsPage.
    
    Annonce: "Label : Valeur(s)" (ex: "Adresse IP du VPN : 37.19.199.137")
    """

    @property
    def name(self):
        automationId = get_automation_id(self)
        label, values = extract_connection_details_label_and_values(self)
        
        if values:
            values_str = ", ".join(values)
            result = f"{label} : {values_str}"
        else:
            result = label
        
        if DEBUG_MODE:
            log.info(f"PROTONVPN: ConnectionDetailsButton.name → \"{result}\" (ID={automationId})")
        
        return result


class ProtonVPNOverlayPromoButton(UIA):
    """
    Overlay pour la carte promo dans OverlayMessage.
    
    Construit dynamiquement un label à partir des descendants Text.
    """

    @property
    def name(self):
        promo_text = extract_overlay_promo_text(self)
        
        if DEBUG_MODE:
            log.info(f"PROTONVPN: OverlayPromoButton.name → \"{promo_text[:60]}...\"")
        
        return promo_text


class ProtonVPNPlusPromoButton(UIA):
    """
    Overlay pour le bouton VPN Plus promo.
    
    - name = "Passer à VPN Plus" (court, pour le focus)
    - description = texte marketing long (accessible via NVDA+Tab ou Ctrl+Shift+L)
    """
    
    _cached_long_text = None

    @property
    def name(self):
        return _("Upgrade to VPN Plus")
    
    @property
    def description(self):
        """Retourne le texte marketing long pour NVDA+Tab."""
        if self._cached_long_text:
            return self._cached_long_text
        
        long_text = extract_vpn_plus_long_text(self)
        self._cached_long_text = long_text
        
        if DEBUG_MODE:
            log.info(f"PROTONVPN: VPNPlusPromoButton.description → \"{long_text[:80]}...\"")
        
        return long_text


class ProtonVPNWidgetButton(UIA):
    """Overlay pour les widgets colonne droite."""

    @property
    def name(self):
        original_name = super().name or ""
        
        if original_name and len(original_name.strip()) > 2:
            if original_name not in (_("ProtonVPN widget button"), _("ProtonVPN button"), _("Unnamed button")):
                return original_name

        index = count_same_type_siblings_before(self)

        if index == 0:
            label = _("NetShield")
        elif index == 1:
            label = _("Kill Switch")
        elif index == 2:
            label = _("Split tunneling")
        else:
            rect = get_bounding_rect(self)
            if rect:
                y = rect[1]
                if y < 200:
                    label = _("NetShield")
                elif y < 400:
                    label = _("Kill Switch")
                else:
                    label = _("Split tunneling")
            else:
                label = _("Widget {}").format(index + 1)
        
        if DEBUG_MODE:
            log.info(f"PROTONVPN: WidgetButton.name → \"{label}\" (index={index})")
        
        return label


class ProtonVPNSideWidgetButton(UIA):
    """Overlay pour les widgets avec AutomationId spécifique."""

    AUTOMATION_ID_MAPPING = {
        "PortForwardingWidgetButton": _("Port forwarding"),
        "SettingsButton": _("Settings"),
        "TitleBarMenuButton": _("Main menu"),
    }

    @property
    def name(self):
        original_name = super().name or ""
        automationId = get_automation_id(self)

        if original_name and len(original_name.strip()) > 0:
            if original_name not in (_("ProtonVPN widget button"), _("ProtonVPN button")):
                return original_name

        if automationId in self.AUTOMATION_ID_MAPPING:
            return self.AUTOMATION_ID_MAPPING[automationId]

        if automationId:
            return _("Button {}").format(automationId)

        return _("ProtonVPN button")


class ProtonVPNGenericButton(UIA):
    """Overlay générique pour les boutons sans nom (fallback)."""

    @property
    def name(self):
        original_name = super().name or ""
        automationId = get_automation_id(self)

        if original_name and len(original_name.strip()) > 2:
            return original_name

        if automationId:
            return _("Button ({})").format(automationId)

        return _("Unnamed button")


# ============================================================================
# CLASSE APPMODULE
# ============================================================================
log.info("PROTONVPN: Defining AppModule class...")


class AppModule(appModuleHandler.AppModule):
    """Module d'application NVDA pour ProtonVPN."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        log.info("=" * 60)
        log.info("PROTONVPN: AppModule v1.0.0 loaded!")
        log.info(f"PROTONVPN: DEBUG_MODE = {DEBUG_MODE}")
        log.info("=" * 60)
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
                
                # 4) WidgetButton
                elif automationId == "WidgetButton":
                    clsList.insert(0, ProtonVPNWidgetButton)
                
                # 5) Autres widgets spécifiques
                elif automationId in ("PortForwardingWidgetButton", "SettingsButton", "TitleBarMenuButton"):
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
    
    def _find_element_by_automation_id(self, target_id, max_depth=10):
        """
        Recherche un élément UIA par AutomationId dans l'arbre.
        Retourne l'objet NVDA ou None.
        """
        try:
            from NVDAObjects import NVDAObject
            import UIAHandler
            
            # Obtenir la fenêtre principale
            fg = api.getForegroundObject()
            if not fg:
                return None
            
            # Rechercher récursivement
            def search(obj, depth):
                if depth > max_depth:
                    return None
                try:
                    if get_automation_id(obj) == target_id:
                        return obj
                    for child in obj.children:
                        result = search(child, depth + 1)
                        if result:
                            return result
                except:
                    pass
                return None
            
            return search(fg, 0)
        except Exception as e:
            log.error(f"PROTONVPN: _find_element_by_automation_id error: {e}")
            return None
    
    def _invoke_element(self, obj):
        """Invoque un élément (clic/appui Entrée)."""
        try:
            if hasattr(obj, 'UIAElement') and obj.UIAElement:
                # Essayer InvokePattern
                try:
                    import UIAHandler
                    pattern = obj.UIAElement.GetCurrentPattern(UIAHandler.UIA_InvokePatternId)
                    if pattern:
                        pattern.QueryInterface(UIAHandler.IUIAutomationInvokePattern).Invoke()
                        return True
                except:
                    pass
            
            # Fallback: doAction
            try:
                obj.doAction()
                return True
            except:
                pass
            
            # Fallback: focus + Enter
            try:
                obj.setFocus()
                import time
                time.sleep(0.1)
                import winUser
                winUser.sendMessage(obj.windowHandle, 0x0100, 0x0D, 0)  # WM_KEYDOWN VK_RETURN
                winUser.sendMessage(obj.windowHandle, 0x0101, 0x0D, 0)  # WM_KEYUP VK_RETURN
                return True
            except:
                pass
            
            return False
        except Exception as e:
            log.error(f"PROTONVPN: _invoke_element error: {e}")
            return False
    
    def script_toggleVPN(self, gesture):
        """Connecter ou déconnecter le VPN."""
        log.info("PROTONVPN: script_toggleVPN triggered!")
        
        # Chercher d'abord le bouton Déconnecter (si VPN connecté)
        btn = self._find_element_by_automation_id("ConnectionCardDisconnectButton")
        is_disconnecting = True
        
        if not btn:
            # Sinon chercher le bouton Connecter (VPN déconnecté)
            btn = self._find_element_by_automation_id("ConnectionCardConnectButton")
            is_disconnecting = False
        
        if not btn:
            # Fallback : chercher par Name
            log.info("PROTONVPN: Searching buttons by name...")
            fg = api.getForegroundObject()
            if fg:
                def find_by_name(obj, depth=0):
                    if depth > 15:
                        return None
                    try:
                        name = (obj.name or "").lower()
                        if obj.role == controlTypes.Role.BUTTON:
                            if "déconnecter" in name or "disconnect" in name:
                                return (obj, True)
                            elif "connecter" in name or "connect" in name:
                                return (obj, False)
                        for child in obj.children:
                            result = find_by_name(child, depth + 1)
                            if result:
                                return result
                    except:
                        pass
                    return None
                
                result = find_by_name(fg)
                if result:
                    btn, is_disconnecting = result
        
        if not btn:
            ui.message(_("Connection button not found"))
            log.error("PROTONVPN: Neither Connect nor Disconnect button found")
            return
        
        # Annoncer immédiatement l'action
        if is_disconnecting:
            ui.message(_("Disconnecting"))
            log.info("PROTONVPN: Disconnecting VPN...")
        else:
            ui.message(_("Connecting"))
            log.info("PROTONVPN: Connecting VPN...")
        
        # Invoquer le bouton
        if self._invoke_element(btn):
            log.info("PROTONVPN: Button invoked successfully")
            # Lancer la confirmation d'état en différé
            try:
                import wx
                wx.CallLater(1500, self._confirm_vpn_state, is_disconnecting)
            except:
                # Si wx n'est pas dispo, ignorer la confirmation
                pass
        else:
            ui.message(_("Action unavailable"))
    
    def _confirm_vpn_state(self, was_disconnecting):
        """Confirme l'état du VPN après l'action (appelé en différé)."""
        try:
            # Vérifier si le bouton opposé est maintenant visible
            if was_disconnecting:
                # On vient de déconnecter, on devrait voir le bouton Connect
                btn = self._find_element_by_automation_id("ConnectionCardConnectButton")
                if btn:
                    ui.message(_("VPN disconnected"))
                    log.info("PROTONVPN: VPN disconnected confirmed")
            else:
                # On vient de connecter, on devrait voir le bouton Disconnect
                btn = self._find_element_by_automation_id("ConnectionCardDisconnectButton")
                if btn:
                    ui.message(_("VPN connected"))
                    log.info("PROTONVPN: VPN connected confirmed")
        except Exception as e:
            log.error(f"PROTONVPN: _confirm_vpn_state error: {e}")
    
    script_toggleVPN.__doc__ = _("Toggle VPN connection")
    script_toggleVPN.category = "ProtonVPN"
    
    def script_toggleKillSwitch(self, gesture):
        """Activer ou désactiver le Kill Switch."""
        log.info("PROTONVPN: script_toggleKillSwitch triggered!")
        
        # Le Kill Switch est accessible via WidgetButton (index 1 dans les widgets)
        # On cherche via les éléments avec AutomationId == "WidgetButton"
        try:
            fg = api.getForegroundObject()
            if not fg:
                ui.message(_("Action unavailable"))
                return
            
            # Chercher tous les WidgetButton
            widgets = []
            def find_widgets(obj, depth=0):
                if depth > 15:
                    return
                try:
                    if get_automation_id(obj) == "WidgetButton":
                        widgets.append(obj)
                    for child in obj.children:
                        find_widgets(child, depth + 1)
                except:
                    pass
            
            find_widgets(fg)
            
            # Le Kill Switch est généralement le 2ème widget (index 1)
            if len(widgets) >= 2:
                kill_switch_btn = widgets[1]
                ui.message(_("Kill Switch"))
                if self._invoke_element(kill_switch_btn):
                    log.info("PROTONVPN: Kill Switch toggled")
                else:
                    ui.message(_("Action unavailable"))
            else:
                ui.message(_("Kill Switch not found"))
        except Exception as e:
            log.error(f"PROTONVPN: script_toggleKillSwitch error: {e}")
            ui.message(_("Action unavailable"))
    
    script_toggleKillSwitch.__doc__ = _("Toggle Kill Switch")
    script_toggleKillSwitch.category = "ProtonVPN"
    
    def script_openCountrySelector(self, gesture):
        """Ouvrir le sélecteur de pays."""
        log.info("PROTONVPN: script_openCountrySelector triggered!")
        
        # Chercher le bouton de sélection de pays
        # C'est généralement le premier bouton sous LocationDetailsPage (index 1 = Pays)
        try:
            fg = api.getForegroundObject()
            if not fg:
                ui.message(_("Action unavailable"))
                return
            
            # Chercher les boutons sous LocationDetailsPage
            location_btns = []
            def find_location_btns(obj, depth=0):
                if depth > 15:
                    return
                try:
                    if is_location_details_dynamic_button(obj):
                        location_btns.append(obj)
                    for child in obj.children:
                        find_location_btns(child, depth + 1)
                except:
                    pass
            
            find_location_btns(fg)
            
            # Le bouton Pays est généralement le 2ème (index 1)
            if len(location_btns) >= 2:
                country_btn = location_btns[1]
                ui.message(_("Country selector"))
                if self._invoke_element(country_btn):
                    log.info("PROTONVPN: Country selector opened")
                else:
                    ui.message(_("Action unavailable"))
            else:
                ui.message(_("Country selector not found"))
        except Exception as e:
            log.error(f"PROTONVPN: script_openCountrySelector error: {e}")
            ui.message(_("Action unavailable"))
    
    script_openCountrySelector.__doc__ = _("Open country selector")
    script_openCountrySelector.category = "ProtonVPN"
    
    def script_announceTraffic(self, gesture):
        """Annoncer les informations de trafic."""
        log.info("PROTONVPN: script_announceTraffic triggered!")
        
        try:
            fg = api.getForegroundObject()
            if not fg:
                ui.message(_("Action unavailable"))
                return
            
            traffic_info = []
            
            # Chercher les boutons de trafic sous ConnectionDetailsPage
            def find_traffic_btns(obj, depth=0):
                if depth > 15:
                    return
                try:
                    if is_connection_details_dynamic_button(obj):
                        automationId = get_automation_id(obj)
                        # ShowVolumeFlyoutButton = Trafic total
                        # E = Trafic actuel
                        if automationId in ("ShowVolumeFlyoutButton", "E"):
                            label, values = extract_connection_details_label_and_values(obj)
                            if values:
                                traffic_info.append(f"{label} : {', '.join(values)}")
                    for child in obj.children:
                        find_traffic_btns(child, depth + 1)
                except:
                    pass
            
            find_traffic_btns(fg)
            
            if traffic_info:
                message = ". ".join(traffic_info)
                ui.message(message)
                log.info(f"PROTONVPN: Traffic announced: {message}")
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
    }


log.info("PROTONVPN: AppModule class defined successfully")
log.info("=" * 60)

