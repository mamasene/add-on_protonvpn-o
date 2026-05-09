# -*- coding: utf-8 -*-
"""
Global Plugin - ProtonVPN Bridge
Enregistre explicitement le mapping entre les executables ProtonVPN et l'AppModule.

IMPORTANT: Le processus principal de l'interface graphique ProtonVPN est:
    ProtonVPN.Client.exe

Ce plugin mappe ce nom vers notre AppModule.
"""

import globalPluginHandler
import appModuleHandler
from logHandler import log

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    """Global plugin pour enregistrer le mapping ProtonVPN."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        log.info("=" * 60)
        log.info("PROTONVPN BRIDGE: Global plugin loading...")
        
        # Le processus principal est ProtonVPN.Client.exe
        # NVDA convertit en minuscules et enleve .exe
        # Donc "ProtonVPN.Client.exe" devient "protonvpn.client"
        
        try:
            # ProtonVPN.Client.exe -> protonvpnservice (notre module principal)
            appModuleHandler.registerExecutableWithAppModule("protonvpn.client", "protonvpnservice")
            log.info("PROTONVPN BRIDGE: Registered 'protonvpn.client' -> 'protonvpnservice'")
        except Exception as e:
            log.error(f"PROTONVPN BRIDGE: Failed to register protonvpn.client: {e}")
        
        try:
            # ProtonVPNService.exe (service backend)
            appModuleHandler.registerExecutableWithAppModule("protonvpnservice", "protonvpnservice")
            log.info("PROTONVPN BRIDGE: Registered 'protonvpnservice' -> 'protonvpnservice'")
        except Exception as e:
            log.error(f"PROTONVPN BRIDGE: Failed to register protonvpnservice: {e}")
        
        try:
            # ProtonVPN.exe (au cas ou)
            appModuleHandler.registerExecutableWithAppModule("protonvpn", "protonvpnservice")
            log.info("PROTONVPN BRIDGE: Registered 'protonvpn' -> 'protonvpnservice'")
        except Exception as e:
            log.error(f"PROTONVPN BRIDGE: Failed to register protonvpn: {e}")
        
        log.info("PROTONVPN BRIDGE: Global plugin loaded successfully!")
        log.info("=" * 60)

    def terminate(self, *args, **kwargs):
        """Nettoyage lors de la fermeture du plugin."""
        log.info("PROTONVPN BRIDGE: Global plugin terminating...")
        
        try:
            appModuleHandler.unregisterExecutable("protonvpn.client")
        except Exception:
            pass
        
        try:
            appModuleHandler.unregisterExecutable("protonvpnservice")
        except Exception:
            pass
        
        try:
            appModuleHandler.unregisterExecutable("protonvpn")
        except Exception:
            pass
        
        super().terminate(*args, **kwargs)
        log.info("PROTONVPN BRIDGE: Global plugin terminated")
