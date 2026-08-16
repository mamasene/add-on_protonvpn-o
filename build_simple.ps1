# Build script NVDA Add-on ProtonVPN
# Usage: .\build_simple.ps1
#
# buildVars.py is the single source of truth for version and metadata.
# Nothing in this script hardcodes them.

$ErrorActionPreference = "Stop"

$addonName = "protonVPNAccessibility"

Write-Host "=== NVDA Add-on Build Script ===" -ForegroundColor Cyan

# =========================
# MANIFEST + VERSION
# =========================
Write-Host "Generating manifest from buildVars.py..."
$addonVersion = (python tools\generate_manifest.py).Trim()
if ($LASTEXITCODE -ne 0) { throw "Manifest generation failed." }
if ([string]::IsNullOrWhiteSpace($addonVersion)) { throw "Could not read version from buildVars.py." }

$outputFile = "$addonName-$addonVersion.nvda-addon"
Write-Host "Building: $outputFile"

# =========================
# DOSSIERS DOC
# =========================
# addon/doc/en/readme.html and addon/doc/fr/readme.html are committed static
# files and are never regenerated: the curated HTML is the deliverable.
foreach ($lang in @("en", "fr")) {
    $docDir = "addon\doc\$lang"
    if (-not (Test-Path $docDir)) {
        New-Item -ItemType Directory -Path $docDir -Force | Out-Null
    }
    if (-not (Test-Path "$docDir\readme.html")) {
        throw "Missing documentation file: $docDir\readme.html"
    }
}
Write-Host "Using committed static HTML documentation (en + fr)."

# =========================
# CATALOGUES LOCALE (.po -> .mo)
# =========================
Write-Host "Compiling locale catalogs..."
python tools\compile_po.py
if ($LASTEXITCODE -ne 0) { throw "Locale compilation failed." }

# Translated store metadata (summary, description, changelog) per language.
Write-Host "Generating translated manifests..."
python tools\generate_translated_manifests.py
if ($LASTEXITCODE -ne 0) { throw "Translated manifest generation failed." }

# =========================
# PACKAGE
# =========================
# Exclusions and file layout live in tools/package.py, shared with sconstruct,
# so both build entry points produce the same package.
Write-Host "Creating package..."
python tools\package.py | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Packaging failed." }
if (-not (Test-Path $outputFile)) { throw "Expected package not found: $outputFile" }

# =========================
# FIN
# =========================
Write-Host ""
Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host "Output: $outputFile"
Write-Host ""
Write-Host "Installation NVDA :"
Write-Host "1. Ouvrir le menu NVDA"
Write-Host "2. Aller dans Outils -> Add-on Store"
Write-Host "3. Acceder a l'onglet Extensions disponibles"
Write-Host "4. Rechercher : ProtonVPN Accessibility"
Write-Host "5. Selectionner l'extension puis choisir Installer"
Write-Host "6. Redemarrer NVDA"
