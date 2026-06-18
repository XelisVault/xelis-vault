#!/usr/bin/env python3
"""
XELIS Vault v4.2 — One-Command Installer

Ultra-simple installer for anyone (Linux, macOS, Windows).
One command in the terminal does everything:

    1. Checks prerequisites (Python, XELIS daemon, etc.)
    2. Downloads and installs XELIS daemon/wallet if needed
    3. Asks user: create new wallet or import existing
    4. Asks what the user wants to do:
       - Be a price provider (stake VLT, submit price, earn rewards)
       - Be a user (deposit XEL, borrow xUSD, swap)
       - Be a miner (mine XEL + run keeper)
       - Do everything
    5. Automatically configures systemd/launchd/Windows Service scripts
    6. Shows a summary and starts services

USAGE (single command):

    On Linux / macOS:
        curl -fsSL https://raw.githubusercontent.com/XelisVault/xelis-vault/main/install.py | python3

    On Windows (PowerShell):
        iwr -useb https://raw.githubusercontent.com/XelisVault/xelis-vault/main/install.py | python

    Or locally after download:
        python3 install.py

The installer is 100% interactive and guided. No technical knowledge
required. Answer a few questions and everything is configured
automatically.
"""
import os
import sys
import platform
import subprocess
import shutil
import json
import time
import urllib.request
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================
VAULT_DIR = Path.home() / ".xelis-vault"
VAULT_BIN_DIR = VAULT_DIR / "bin"
VAULT_SCRIPTS_DIR = VAULT_DIR / "scripts"
VAULT_CONFIG_FILE = VAULT_DIR / "config.json"
VAULT_ENV_FILE = VAULT_DIR / ".env"

REPO_URL = "https://raw.githubusercontent.com/XelisVault/xelis-vault/main"
XELIS_RELEASES_URL = "https://github.com/xelis-project/xelis-blockchain/releases"

# Colors (disabled on Windows cmd)
IS_TTY = sys.stdout.isatty()
if IS_TTY and platform.system() != "Windows":
    class Colors:
        HEADER = '\033[95m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        RED = '\033[91m'
        BOLD = '\033[1m'
        END = '\033[0m'
else:
    class Colors:
        HEADER = BLUE = CYAN = GREEN = YELLOW = RED = BOLD = END = ''


# ============================================================================
# UTILITIES
# ============================================================================
def c(text: str, color: str) -> str:
    return f"{color}{text}{Colors.END}"

def info(msg: str):
    print(f"{c('ℹ', Colors.BLUE)} {msg}")

def success(msg: str):
    print(f"{c('✓', Colors.GREEN)} {msg}")

def warn(msg: str):
    print(f"{c('!', Colors.YELLOW)} {msg}")

def error(msg: str):
    print(f"{c('✗', Colors.RED)} {msg}")

def header(msg: str):
    print()
    print(c("=" * 70, Colors.CYAN))
    print(c(f"  {msg}", Colors.BOLD))
    print(c("=" * 70, Colors.CYAN))
    print()

def prompt(msg: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    return input(f"{c('>', Colors.CYAN)} {msg}{suffix}: ").strip() or default

def confirm(msg: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    r = input(f"{c('?', Colors.CYAN)} {msg} [{d}]: ").strip().lower()
    if not r:
        return default
    return r in ("y", "yes", "o", "oui")

def pause(msg: str = "Press Enter to continue..."):
    input(msg)


# ============================================================================
# PLATFORM DETECTION
# ============================================================================
def detect_platform() -> dict:
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return {"os": "linux", "arch": "x86_64", "binary_suffix": ""}
        elif machine in ("aarch64", "arm64"):
            return {"os": "linux", "arch": "aarch64", "binary_suffix": ""}
    elif system == "Darwin":
        if machine in ("x86_64", "amd64"):
            return {"os": "macos", "arch": "x86_64", "binary_suffix": ""}
        elif machine in ("arm64", "aarch64"):
            return {"os": "macos", "arch": "arm64", "binary_suffix": ""}
    elif system == "Windows":
        return {"os": "windows", "arch": "x86_64", "binary_suffix": ".exe"}

    return {"os": "unknown", "arch": "unknown", "binary_suffix": ""}


# ============================================================================
# CHECK PREREQUISITES
# ============================================================================
def check_python_version() -> bool:
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        error(f"Python 3.8+ required, you have {version.major}.{version.minor}")
        return False
    success(f"Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def install_pip_package(package: str):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "--quiet", package])
        success(f"Installed {package}")
    except subprocess.CalledProcessError:
        error(f"Failed to install {package}")


def check_xelis_daemon() -> bool:
    return check_command("xelis_daemon")


def check_xelis_wallet() -> bool:
    return check_command("xelis_wallet")


def check_xelis_miner() -> bool:
    return check_command("xelis_miner")


# ============================================================================
# DIRECTORY SETUP
# ============================================================================
def setup_directories():
    info("Setting up directories...")
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_BIN_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    success(f"Created {VAULT_DIR}")


# ============================================================================
# XELIS INSTALLATION
# ============================================================================
def install_xelis(platform_info: dict):
    """Guide the user to install XELIS daemon/wallet/miner."""
    header("XELIS INSTALLATION")

    system = platform_info["os"]

    if check_xelis_daemon() and check_xelis_wallet():
        success("XELIS daemon and wallet already installed")
        return True

    print()
    info("XELIS daemon is not installed on this system.")
    print()
    print("Installation options:")
    print()
    print("  1. Build from source (recommended, requires Rust)")
    print("  2. Download precompiled binaries")
    print("  3. Use Docker")
    print("  4. I already have XELIS but it is not in my PATH")
    print("  5. Later — I just want to see the XELIS Vault scripts")
    print()

    choice = prompt("Your choice", "1")

    if choice == "1":
        return install_xelis_from_source()
    elif choice == "2":
        return install_xelis_precompiled(platform_info)
    elif choice == "3":
        return install_xelis_docker()
    elif choice == "4":
        path = prompt("Path to XELIS binaries (e.g. /usr/local/bin)")
        if path and Path(path).exists():
            info(f"Add {path} to your PATH and re-run the installer")
            return False
        return False
    else:
        info("OK, continuing with just the XELIS Vault scripts")
        return False


def install_xelis_from_source() -> bool:
    info("Installing from source...")

    if not check_command("cargo"):
        print()
        warn("Rust is not installed. To install Rust:")
        print()
        print("  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
        print()
        if not confirm("Install Rust now?"):
            return False
        try:
            subprocess.check_call(
                "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                shell=True
            )
            # Source cargo env
            cargo_env = Path.home() / ".cargo" / "env"
            if cargo_env.exists():
                os.environ["PATH"] = f"{Path.home() / '.cargo' / 'bin'}:{os.environ.get('PATH', '')}"
            success("Rust installed")
        except subprocess.CalledProcessError:
            error("Rust installation failed")
            return False

    # Clone and build
    clone_dir = VAULT_DIR / "xelis-blockchain"
    if not clone_dir.exists():
        info("Cloning XELIS blockchain repo...")
        try:
            subprocess.check_call(
                ["git", "clone", "--depth", "1",
                 "https://github.com/xelis-project/xelis-blockchain.git",
                 str(clone_dir)]
            )
        except subprocess.CalledProcessError:
            error("Clone failed")
            return False

    info("Compilation (may take 10-20 minutes)...")
    try:
        subprocess.check_call(
            ["cargo", "build", "--release",
             "--bin", "xelis_daemon",
             "--bin", "xelis_wallet",
             "--bin", "xelis_miner"],
            cwd=clone_dir
        )
    except subprocess.CalledProcessError:
        error("Compilation failed")
        return False

    # Copy binaries to ~/.xelis-vault/bin
    for binary in ["xelis_daemon", "xelis_wallet", "xelis_miner"]:
        src = clone_dir / "target" / "release" / binary
        dst = VAULT_BIN_DIR / binary
        shutil.copy2(src, dst)
        os.chmod(dst, 0o755)

    success("XELIS daemon, wallet and miner installed")
    info(f"Binaries at: {VAULT_BIN_DIR}")
    info(f"Add this folder to your PATH:")
    print(f"  export PATH=\"{VAULT_BIN_DIR}:$PATH\"")
    return True


def install_xelis_precompiled(platform_info: dict) -> bool:
    info("Downloading precompiled binaries...")
    print()
    print(f"Please manually download the binaries from:")
    print(f"  {XELIS_RELEASES_URL}")
    print()
    print(f"Place them in: {VAULT_BIN_DIR}")
    print()
    pause("Press Enter once the binaries are placed...")

    # Verify
    if check_xelis_daemon() or (VAULT_BIN_DIR / "xelis_daemon").exists():
        success("XELIS binaries found")
        return True
    warn("Binaries not found. Continuing anyway.")
    return False


def install_xelis_docker() -> bool:
    if not check_command("docker"):
        error("Docker is not installed. Install Docker first: https://docs.docker.com/get-docker/")
        return False

    info("Configuring Docker for XELIS...")
    docker_script = VAULT_DIR / "docker-compose.yml"

    docker_content = """version: '3'
services:
  xelis-daemon:
    image: xelis/xelis-daemon:latest
    ports:
      - "8080:8080"
      - "2125:2125"
    volumes:
      - ./data:/root/.xelis
    command: --network testnet
    restart: unless-stopped
"""
    docker_script.write_text(docker_content)
    success(f"Docker compose created: {docker_script}")
    info("Start with: docker-compose up -d")
    return True


# ============================================================================
# WALLET SETUP
# ============================================================================
def setup_wallet() -> dict:
    """Ask user if they want to create or import a wallet."""
    header("WALLET SETUP")

    print("You need an XELIS wallet to:")
    print("  - Receive funds from the faucet (testnet)")
    print("  - Stake VLT (if price provider)")
    print("  - Sign transactions")
    print()

    wallet_info = {"address": "", "name": "", "is_new": False}

    if not check_xelis_wallet():
        warn("xelis_wallet is not available. You will need to configure your wallet manually.")
        wallet_info["address"] = prompt("Enter your XELIS address (xet1... for testnet)")
        return wallet_info

    print("Options:")
    print("  1. Create a new wallet")
    print("  2. Import an existing wallet (via seed phrase)")
    print("  3. I already have a wallet configured in xelis_wallet")
    print()

    choice = prompt("Your choice", "1")

    if choice == "1":
        wallet_info["name"] = prompt("Wallet name", "xelis-vault")
        wallet_info["is_new"] = True
        print()
        info("To create the wallet, run these commands in another terminal:")
        print()
        print(f"  xelis_wallet --network testnet")
        print(f"  > create-wallet {wallet_info['name']}")
        print()
        warn("⚠ BACK UP your seed phrase (12-24 words) — this is your only backup!")
        print()
        wallet_info["address"] = prompt("Once created, paste your address (xet1...)")

    elif choice == "2":
        wallet_info["name"] = prompt("Wallet name", "xelis-vault")
        print()
        info("To import your wallet, run:")
        print()
        print(f"  xelis_wallet --network testnet")
        print(f"  > restore-wallet {wallet_info['name']}")
        print()
        info("Enter your seed phrase when prompted.")
        print()
        wallet_info["address"] = prompt("Once imported, paste your address (xet1...)")

    else:
        wallet_info["name"] = prompt("Existing wallet name", "default")
        wallet_info["address"] = prompt("Wallet address (xet1...)")

    if wallet_info["address"]:
        success(f"Wallet configured: {wallet_info['address']}")

    return wallet_info


# ============================================================================
# ROLE SELECTION
# ============================================================================
def select_role() -> list:
    """Ask the user what they want to do."""
    header("WHAT DO YOU WANT TO DO?")

    print("XELIS Vault offers several roles. You can choose multiple.")
    print()

    roles = []
    if confirm("Be a PRICE PROVIDER (stake 100 VLT, submit prices, earn rewards)?"):
        roles.append("provider")
    if confirm("Be a USER (deposit XEL, borrow xUSD, swap on VaultSwap)?"):
        roles.append("user")
    if confirm("Be a MINER (mine XEL + help the oracle by running the keeper)?"):
        roles.append("miner")
    if confirm("Run a KEEPER only (no stake, helps the oracle, public good)?"):
        roles.append("keeper")

    if not roles:
        warn("No role selected. You can run the installer again later.")
    else:
        success(f"Roles selected: {', '.join(roles)}")

    return roles


# ============================================================================
# SCRIPTS DOWNLOAD
# ============================================================================
def download_scripts(roles: list):
    """Download necessary scripts based on roles."""
    header("SCRIPT DOWNLOAD")

    scripts_to_download = []
    if "provider" in roles:
        scripts_to_download.append("price_provider.py")
    if "keeper" in roles or "miner" in roles:
        scripts_to_download.append("aggregation_keeper.py")

    if not scripts_to_download:
        info("No scripts to download for selected roles")
        return

    for script in scripts_to_download:
        url = f"{REPO_URL}/scripts/{script}"
        dst = VAULT_SCRIPTS_DIR / script
        info(f"Downloading {script}...")
        try:
            urllib.request.urlretrieve(url, dst)
            os.chmod(dst, 0o755)
            success(f"  {dst}")
        except Exception as e:
            # Fallback: copy from local files if available
            local_src = Path(__file__).parent / "scripts" / script
            if local_src.exists():
                shutil.copy2(local_src, dst)
                os.chmod(dst, 0o755)
                success(f"  {dst} (from local file)")
            else:
                error(f"  Failed: {e}")
                warn(f"  Download manually: {url}")


# ============================================================================
# CONFIGURATION GENERATION
# ============================================================================
def generate_config(wallet_info: dict, roles: list, deployment: dict):
    """Generate the configuration file."""
    header("CONFIGURATION GENERATION")

    config = {
        "wallet": wallet_info,
        "roles": roles,
        "network": "testnet",
        "rpc_url": "http://127.0.0.1:8080",
        "contracts": deployment,
        "installed_at": time.time(),
        "version": "v4.2",
    }

    VAULT_CONFIG_FILE.write_text(json.dumps(config, indent=2))
    success(f"Configuration: {VAULT_CONFIG_FILE}")

    # Generate .env file
    env_lines = [
        f"# XELIS Vault v4.2 — Configuration generated by the installer",
        f"# Date: {time.ctime()}",
        f"",
        f"XELIS_NETWORK=testnet",
        f"XELIS_RPC=http://127.0.0.1:8080",
        f"",
        f"# Your wallet",
        f"PROVIDER_ADDRESS={wallet_info.get('address', '')}",
        f"",
        f"# Contracts (from deployment)",
    ]

    for name, addr in deployment.items():
        env_lines.append(f"{name.upper().replace('CONTRACT', 'CONTRACT').replace(' ', '_')}={addr}")

    env_lines.extend([
        f"",
        f"# Provider configuration",
        f"SUBMIT_INTERVAL=20",
        f"PROMETHEUS_PORT=9091",
        f"LOG_LEVEL=INFO",
    ])

    VAULT_ENV_FILE.write_text("\n".join(env_lines))
    success(f"Environment variables: {VAULT_ENV_FILE}")


# ============================================================================
# SERVICE INSTALLATION
# ============================================================================
def install_services(roles: list, platform_info: dict):
    """Install systemd/launchd/Windows services for auto-start."""
    header("SERVICE INSTALLATION")

    system = platform_info["os"]

    services = []
    if "provider" in roles:
        services.append({
            "name": "xelis-vault-provider",
            "description": "XELIS Vault Price Provider",
            "script": "price_provider.py",
            "env_file": True,
        })
    if "keeper" in roles or "miner" in roles:
        services.append({
            "name": "xelis-vault-keeper",
            "description": "XELIS Vault Aggregation Keeper",
            "script": "aggregation_keeper.py",
            "env_file": True,
        })

    if not services:
        info("No services to install")
        return

    if system == "linux":
        install_systemd_services(services)
    elif system == "macos":
        install_launchd_services(services)
    elif system == "windows":
        install_windows_services(services)
    else:
        warn(f"Unsupported OS for automatic service installation: {system}")
        info("You will need to run scripts manually.")


def install_systemd_services(services: list):
    for svc in services:
        unit_path = Path(f"/etc/systemd/system/{svc['name']}.service")
        unit_content = f"""[Unit]
Description={svc['description']}
After=network.target

[Service]
Type=simple
User={os.getenv('USER', 'root')}
WorkingDirectory={VAULT_SCRIPTS_DIR}
EnvironmentFile={VAULT_ENV_FILE}
ExecStart={sys.executable} {VAULT_SCRIPTS_DIR / svc['script']}
Restart=always
RestartSec=10
StandardOutput=append:/var/log/{svc['name']}.log
StandardError=append:/var/log/{svc['name']}.log

[Install]
WantedBy=multi-user.target
"""
        try:
            unit_path.write_text(unit_content)
            success(f"systemd service created: {unit_path}")
            info(f"To start:")
            print(f"  sudo systemctl daemon-reload")
            print(f"  sudo systemctl enable {svc['name']}")
            print(f"  sudo systemctl start {svc['name']}")
        except PermissionError:
            warn(f"Permission denied creating {unit_path}")
            alt_path = VAULT_DIR / f"{svc['name']}.service"
            alt_path.write_text(unit_content)
            info(f"Service file created at: {alt_path}")
            info(f"To install: sudo cp {alt_path} /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now {svc['name']}")


def install_launchd_services(services: list):
    for svc in services:
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.xelisvault.{svc['name']}.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.xelisvault.{svc['name']}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{VAULT_SCRIPTS_DIR / svc['script']}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{VAULT_SCRIPTS_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{VAULT_DIR / svc['name'] + '.out.log'}</string>
    <key>StandardErrorPath</key>
    <string>{VAULT_DIR / svc['name'] + '.err.log'}</string>
</dict>
</plist>
"""
        plist_path.write_text(plist_content)
        success(f"launchd service created: {plist_path}")
        info(f"To start: launchctl load {plist_path}")


def install_windows_services(services: list):
    for svc in services:
        # Create a .bat to start the script
        bat_path = VAULT_DIR / f"{svc['name']}.bat"
        bat_content = f"""@echo off
cd /d {VAULT_SCRIPTS_DIR}
for /f "delims=" %%i in ({VAULT_ENV_FILE}) do set %%i
{sys.executable} {VAULT_SCRIPTS_DIR / svc['script']}
"""
        bat_path.write_text(bat_content)
        success(f"Batch script created: {bat_path}")
        info(f"To run in the background, use nssm or Task Scheduler:")
        print(f"  nssm install {svc['name']} {bat_path}")
        print(f"  nssm start {svc['name']}")


# ============================================================================
# FAUCET CLAIM
# ============================================================================
def claim_from_faucet(wallet_info: dict, deployment: dict):
    """Guide the user to claim from the faucet."""
    if not wallet_info.get("address"):
        return

    header("TESTNET FAUCET")

    faucet_addr = deployment.get("FaucetContract", "")
    if not faucet_addr:
        warn("Faucet not deployed — contact the XELIS Vault team for testnet funds")
        return

    print(f"You can claim from the testnet faucet:")
    print(f"  100 XEL testnet (per 24h)")
    print(f"  200 VLT (per 24h)")
    print()
    print(f"Faucet address: {faucet_addr}")
    print(f"Your wallet    : {wallet_info['address']}")
    print()

    if confirm("Claim now?"):
        info("To claim, run:")
        print()
        print(f"  xelis_wallet --network testnet")
        print(f"  > call-contract {faucet_addr} claim_both --signer {wallet_info.get('name', 'default')}")
        print()
        info("Or via direct RPC:")
        print(f"  curl -X POST http://127.0.0.1:8080 -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"method\":\"submit_transaction\",\"params\":{{\"tx_type\":\"CallContract\",\"contract\":\"{faucet_addr}\",\"entry\":\"claim_both\",\"args\":[],\"signer\":\"{wallet_info['address']}\"}},\"jsonrpc\":\"2.0\",\"id\":1}}'")


# ============================================================================
# PROVIDER REGISTRATION
# ============================================================================
def register_provider(wallet_info: dict, deployment: dict, roles: list):
    """Guide the user to stake and become a provider."""
    if "provider" not in roles:
        return

    header("BECOME A PRICE PROVIDER")

    oracle_addr = deployment.get("StakedOracle", "")
    vlt_asset = deployment.get("VLTAsset", "")

    print(f"To become a price provider:")
    print(f"  1. Get 100 VLT (from faucet or by buying)")
    print(f"  2. Stake 100 VLT via StakedOracle.register_provider()")
    print(f"  3. Run the price_provider.py script")
    print()
    print(f"StakedOracle address: {oracle_addr}")
    print(f"VLT asset hash      : {vlt_asset}")
    print()

    if confirm("Stake now?"):
        info("To stake, run:")
        print()
        print(f"  xelis_wallet --network testnet")
        print(f"  > call-contract {oracle_addr} register_provider \\")
        print(f"      --signer {wallet_info.get('name', 'default')} \\")
        print(f"      --deposit {vlt_asset} 10000000000")
        print()
        info("Once staking is done, the price_provider.py script can start.")


# ============================================================================
# SUMMARY
# ============================================================================
def show_summary(wallet_info: dict, roles: list, deployment: dict):
    header("INSTALLATION COMPLETE")

    print(c("Summary:", Colors.BOLD))
    print()
    print(f"  Wallet address : {wallet_info.get('address', '(not configured)')}")
    print(f"  Wallet name    : {wallet_info.get('name', '(default)')}")
    print(f"  Roles          : {', '.join(roles) if roles else '(none)'}")
    print(f"  Network        : testnet")
    print()
    print(c("Files created:", Colors.BOLD))
    print(f"  Config   : {VAULT_CONFIG_FILE}")
    print(f"  Env      : {VAULT_ENV_FILE}")
    print(f"  Scripts  : {VAULT_SCRIPTS_DIR}")
    print()
    print(c("Deployed contracts:", Colors.BOLD))
    for name, addr in deployment.items():
        print(f"  {name:20s}: {addr}")
    print()
    print(c("Next steps:", Colors.BOLD))
    if "provider" in roles:
        print(f"  → Start the daemon:    xelis_daemon --network testnet")
        print(f"  → Stake 100 VLT:       see instructions above")
        print(f"  → Start the provider:  {VAULT_SCRIPTS_DIR}/price_provider.py")
    if "keeper" in roles or "miner" in roles:
        print(f"  → Start the keeper:    {VAULT_SCRIPTS_DIR}/aggregation_keeper.py")
    if "user" in roles:
        print(f"  → Claim from faucet:   see instructions above")
        print(f"  → Deposit XEL:         xelis_wallet call-contract <VaultEngine> deposit 0x0 <amount>")
    print()
    print(c("Documentation:", Colors.BOLD))
    print(f"  Provider guide : https://github.com/XelisVault/xelis-vault/blob/main/docs/PROVIDER_GUIDE.md")
    print(f"  Miner guide     : https://github.com/XelisVault/xelis-vault/blob/main/docs/MINER_GUIDE.md")
    print(f"  Testnet deploy  : https://github.com/XelisVault/xelis-vault/blob/main/docs/TESTNET_DEPLOYMENT.md")
    print()
    print(c("Support:", Colors.BOLD))
    print(f"  Discord : https://discord.gg/xelisvault")
    print(f"  Email   : support@xelisvault.io")
    print()
    success("Welcome to XELIS Vault! 🚀")


# ============================================================================
# MAIN
# ============================================================================
def main():
    header("XELIS VAULT v4.2 — INSTALLER")
    print(c("Welcome! This installer will configure XELIS Vault for you.", Colors.CYAN))
    print(c("One command, and everything is ready. 🎯", Colors.CYAN))
    print()
    print(c("The installer will:", Colors.BOLD))
    print("  1. Check your system (Python, XELIS)")
    print("  2. Install XELIS daemon/wallet/miner if needed")
    print("  3. Create or import your wallet")
    print("  4. Ask what you want to do (provider, user, miner)")
    print("  5. Download and configure scripts")
    print("  6. Install services for auto-start")
    print("  7. Show final instructions")
    print()

    if not confirm("Continue?", True):
        info("Installation cancelled. See you later!")
        return

    # 1. Platform detection
    platform_info = detect_platform()
    info(f"Detected system: {platform_info['os']} {platform_info['arch']}")

    # 2. Check Python
    if not check_python_version():
        sys.exit(1)

    # 3. Install pip packages
    info("Checking Python dependencies...")
    try:
        import requests
    except ImportError:
        install_pip_package("requests")

    # 4. Setup directories
    setup_directories()

    # 5. Install XELIS if needed
    install_xelis(platform_info)

    # 6. Wallet setup
    wallet_info = setup_wallet()

    # 7. Role selection
    roles = select_role()

    # 8. Download scripts
    download_scripts(roles)

    # 9. Get deployment info (in real scenario, fetched from a known URL)
    # For now, use placeholder
    deployment = {
        "VLTToken": "0x0000000000000000000000000000000000000000 (to fill after deployment)",
        "VLTAsset": "0x0000000000000000000000000000000000000000 (to fill after deployment)",
        "StakedOracle": "0x0000000000000000000000000000000000000000 (to fill after deployment)",
        "VaultEngine": "0x0000000000000000000000000000000000000000 (to fill after deployment)",
        "VaultSwap": "0x0000000000000000000000000000000000000000 (to fill after deployment)",
        "xUSD": "0x0000000000000000000000000000000000000000 (to fill after deployment)",
        "FaucetContract": "0x0000000000000000000000000000000000000000 (to fill after deployment)",
    }

    # 10. Generate config
    generate_config(wallet_info, roles, deployment)

    # 11. Install services
    install_services(roles, platform_info)

    # 12. Faucet claim
    claim_from_faucet(wallet_info, deployment)

    # 13. Provider registration
    register_provider(wallet_info, deployment, roles)

    # 14. Summary
    show_summary(wallet_info, roles, deployment)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        warn("Installation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print()
        error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
