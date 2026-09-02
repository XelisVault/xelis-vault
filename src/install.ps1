# ============================================================================
#  XELIS Vault — Windows PowerShell Installer
# ============================================================================
#  Install:   irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
#  Uninstall: irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
# ============================================================================

param([string]$Args = "")

$ErrorActionPreference = "Stop"
$VERSION = "7.0"
$REPO = "XelisVault/xelis-vault"
$REPO_URL = "https://github.com/$REPO.git"
$INSTALL_DIR = "$env:USERPROFILE\.xelis-vault"
$VENV_DIR = "$INSTALL_DIR\venv"
$CONFIG_DIR = "$INSTALL_DIR\config"
$LOGS_DIR = "$INSTALL_DIR\logs"
$BIN_DIR = "$INSTALL_DIR\bin"

# ── Colors ──────────────────────────────────────────────────────────────────
function Write-Info($msg)    { Write-Host "i  $msg" -ForegroundColor Blue }
function Write-Success($msg) { Write-Host "v  $msg" -ForegroundColor Green }
function Write-Warn($msg)    { Write-Host "!  $msg" -ForegroundColor Yellow }
function Write-Err($msg)     { Write-Host "x  $msg" -ForegroundColor Red }
function Write-Step($msg)    { Write-Host ""; Write-Host "> $msg" -ForegroundColor Magenta }

# ── Banner ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host " ============================================================" -ForegroundColor Cyan
Write-Host "   XELIS Vault v$VERSION — Windows Installer" -ForegroundColor Cyan
Write-Host "   Privacy-First DeFi on XELIS BlockDAG" -ForegroundColor DarkGray
Write-Host " ============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Uninstall ───────────────────────────────────────────────────────────────
if ($Args -eq "--uninstall") {
    Write-Step "Uninstalling XELIS Vault"
    if (Test-Path $INSTALL_DIR) {
        Write-Info "Removing $INSTALL_DIR"
        Remove-Item -Recurse -Force $INSTALL_DIR
        Write-Success "Installation directory removed"
    }
    # Remove from PATH
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -match [regex]::Escape($BIN_DIR)) {
        $newPath = $currentPath -replace [regex]::Escape(";$BIN_DIR"), "" -replace [regex]::Escape("$BIN_DIR;"), "" -replace [regex]::Escape($BIN_DIR), ""
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Success "Removed $BIN_DIR from PATH"
    }
    Write-Host ""
    Write-Success "XELIS Vault uninstalled."
    exit 0
}

# ── Pre-flight checks ───────────────────────────────────────────────────────
Write-Step "Pre-flight checks"

# Check Python
try {
    $pyVersion = python --version 2>&1
    $pyVersionStr = $pyVersion.ToString()
    if ($pyVersionStr -match "Python (\d+)\.(\d+)") {
        $pyMajor = [int]$Matches[1]
        $pyMinor = [int]$Matches[2]
        if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 10)) {
            Write-Err "Python 3.10+ required (found $pyVersionStr)"
            Write-Err "Install from: https://www.python.org/downloads/"
            exit 1
        }
        Write-Success "Python $pyVersionStr"
    } else {
        throw "Cannot parse Python version"
    }
} catch {
    Write-Err "Python 3 is required but not found."
    Write-Err "Install from: https://www.python.org/downloads/"
    Write-Err "Make sure to check 'Add Python to PATH' during installation."
    exit 1
}

# Check git
try {
    $gitVersion = git --version 2>&1
    Write-Success "git available"
} catch {
    Write-Err "git is required but not found."
    Write-Err "Install from: https://git-scm.com/download/win"
    exit 1
}

Write-Success "Platform: Windows $([System.Environment]::Is64BitOperatingSystem)"

# ── Existing installation ───────────────────────────────────────────────────
if (Test-Path "$INSTALL_DIR\src\.git") {
    Write-Warn "XELIS Vault is already installed at $INSTALL_DIR"
    $answer = Read-Host "?  Update existing installation? [Y/n]"
    if ($answer -eq "" -or $answer -match "^[Yy]$") {
        Write-Step "Updating existing installation"
        Set-Location "$INSTALL_DIR\src"
        Write-Info "Pulling latest changes..."
        git pull --ff-only
        Write-Success "Repository updated"
    } else {
        Write-Info "Skipping."
        exit 0
    }
} else {
    # ── Fresh install ──────────────────────────────────────────────────────
    Write-Step "Installing XELIS Vault"

    New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
    Set-Location $INSTALL_DIR

    # Clone repo
    Write-Info "Cloning $REPO..."
    if (Test-Path "src") { Remove-Item -Recurse -Force "src" }
    git clone --depth 1 $REPO_URL src
    Write-Success "Repository cloned to $INSTALL_DIR\src"

    # Create directories
    New-Item -ItemType Directory -Force -Path $CONFIG_DIR | Out-Null
    New-Item -ItemType Directory -Force -Path $LOGS_DIR | Out-Null
    New-Item -ItemType Directory -Force -Path "$INSTALL_DIR\wallet" | Out-Null
    Write-Success "Directories created"
}

Set-Location "$INSTALL_DIR\src"

# ── Virtualenv ──────────────────────────────────────────────────────────────
Write-Step "Setting up Python environment"

if (-not (Test-Path $VENV_DIR)) {
    Write-Info "Creating virtualenv at $VENV_DIR"
    python -m venv $VENV_DIR
    Write-Success "Virtualenv created"
} else {
    Write-Info "Virtualenv already exists"
}

# Install deps
Write-Info "Installing Python dependencies..."
$pipExe = "$VENV_DIR\Scripts\pip.exe"
& $pipExe install --quiet --upgrade pip
& $pipExe install --quiet requests python-dotenv cryptography
Write-Success "Dependencies installed"

# ── Config file ─────────────────────────────────────────────────────────────
Write-Step "Generating configuration"

$configFile = "$CONFIG_DIR\config.json"
if (-not (Test-Path $configFile)) {
    $configJson = @'
{
  "rpc_url": "https://testnet-node.xelis.io/json_rpc",
  "wallet_url": "http://127.0.0.1:18082/json_rpc",
  "wallet_user": "wallet",
  "wallet_pass": "testpass",
  "miner_address": "",
  "miner_endpoint": "",
  "services": "both",
  "compound": false,
  "contracts": {}
}
'@
    $configJson | Out-File -FilePath $configFile -Encoding utf8
    Write-Success "Config written to $configFile"
} else {
    Write-Info "Config already exists at $configFile"
}

# ── Launchers ───────────────────────────────────────────────────────────────
Write-Step "Installing launchers"

New-Item -ItemType Directory -Force -Path $BIN_DIR | Out-Null

# xvault-miner.bat
$xvaultMinerBat = @"
@echo off
"$VENV_DIR\Scripts\python.exe" "$INSTALL_DIR\src\scripts\xvault-miner.py" %*
"@
$xvaultMinerBat | Out-File -FilePath "$BIN_DIR\xvault-miner.bat" -Encoding ascii

# xvault.bat
$xvaultBat = @"
@echo off
"$VENV_DIR\Scripts\python.exe" "$INSTALL_DIR\src\scripts\xvault.py" %*
"@
$xvaultBat | Out-File -FilePath "$BIN_DIR\xvault.bat" -Encoding ascii

# xvault-relayer.bat
$xvaultRelayerBat = @"
@echo off
"$VENV_DIR\Scripts\python.exe" "$INSTALL_DIR\src\scripts\relayer_daemon.py" %*
"@
$xvaultRelayerBat | Out-File -FilePath "$BIN_DIR\xvault-relayer.bat" -Encoding ascii

Write-Success "Launchers installed: xvault-miner.bat, xvault.bat, xvault-relayer.bat"

# Add to PATH
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notmatch [regex]::Escape($BIN_DIR)) {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$BIN_DIR", "User")
    Write-Success "Added $BIN_DIR to PATH"
    Write-Warn "Restart your terminal for PATH changes to take effect"
} else {
    Write-Info "$BIN_DIR already in PATH"
}

# ── Done ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host " ============================================================" -ForegroundColor Green
Write-Host "   XELIS Vault v$VERSION installed successfully!" -ForegroundColor Green
Write-Host " ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host ""
Write-Host "  For miners:" -ForegroundColor Cyan
Write-Host "    xvault-miner"
Write-Host ""
Write-Host "  For community:" -ForegroundColor Cyan
Write-Host "    xvault"
Write-Host ""
Write-Host "  Config: $configFile" -ForegroundColor DarkGray
Write-Host "  Logs:   $LOGS_DIR\miner.log" -ForegroundColor DarkGray
Write-Host "  Source: $INSTALL_DIR\src" -ForegroundColor DarkGray
Write-Host "  Docs:   https://github.com/$REPO" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Happy mining!" -ForegroundColor Magenta
Write-Host ""
