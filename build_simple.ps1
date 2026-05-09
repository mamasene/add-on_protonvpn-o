# Build script NVDA Add-on ProtonVPN (version corrigée encodage)
# Usage: .\build_simple.ps1

$ErrorActionPreference = "Stop"

# Configuration
$addonName = "protonVPNAccessibility"
$addonVersion = "1.0.0"
$outputFile = "$addonName-$addonVersion.nvda-addon"

Write-Host "=== NVDA Add-on Build Script ===" -ForegroundColor Cyan
Write-Host "Building: $outputFile"

# Encodage UTF-8 avec BOM
$utf8BOM = New-Object System.Text.UTF8Encoding $true

# =========================
# MANIFEST (FIX PRINCIPAL)
# =========================
Write-Host "Copying manifest.ini (preserving encoding)..."

if (-not (Test-Path "manifest.ini")) {
    throw "manifest.ini introuvable à la racine du projet."
}

Copy-Item ".\manifest.ini" ".\addon\manifest.ini" -Force

# =========================
# DOSSIERS DOC
# =========================
if (-not (Test-Path "addon\doc\en")) {
    New-Item -ItemType Directory -Path "addon\doc\en" -Force | Out-Null
}
if (-not (Test-Path "addon\doc\fr")) {
    New-Item -ItemType Directory -Path "addon\doc\fr" -Force | Out-Null
}

# =========================
# DOC HTML (static — do not regenerate)
# =========================
# addon/doc/en/readme.html and addon/doc/fr/readme.html are committed static files.
# EN: English documentation.  FR: French translation (do not overwrite).
Write-Host "Using committed static HTML documentation (en + fr)."

# =========================
# CATALOGUES LOCALE (.po -> .mo)
# =========================
Write-Host "Compiling locale catalogs..."
python tools\compile_po.py

# =========================
# CLEAN ANCIEN BUILD
# =========================
if (Test-Path $outputFile) {
    Remove-Item $outputFile -Force
}

# =========================
# PACKAGE
# =========================
Write-Host "Creating package..."

Compress-Archive -Path "addon\*" -DestinationPath "$addonName-$addonVersion.zip" -Force
Rename-Item "$addonName-$addonVersion.zip" $outputFile -Force

# =========================
# FIN
# =========================
Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host "Output: $outputFile"
Write-Host ""
Write-Host "Installation NVDA:"
Write-Host "1. NVDA → Outils → Gérer les modules complémentaires"
Write-Host "2. Installer..."
Write-Host "3. Sélectionner: $outputFile"
Write-Host "4. Redémarrer NVDA"