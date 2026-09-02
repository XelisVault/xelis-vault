# Installation Guide / Guide d'installation / 安装指南 / インストールガイド / دليل التثبيت

---

## English

### Prerequisites

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **git** — [git-scm.com/downloads](https://git-scm.com/downloads/)
- **Windows:** PowerShell 5.1+ or Command Prompt
- **Linux/macOS:** bash, curl

### One-Line Install

**Linux & macOS:**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

**Windows (PowerShell):**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

**Windows (Command Prompt):** download [`install.bat`](install.bat) and double-click it.

### What the installer does

1. Checks Python 3.10+ and git
2. Clones the repo to `~/.xelis-vault/src` (or `%USERPROFILE%\.xelis-vault\src` on Windows)
3. Creates a Python virtual environment
4. Installs dependencies: `requests`, `python-dotenv`, `cryptography`
5. Generates `config/config.json` with testnet defaults
6. Installs launchers: `xvault`, `xvault-miner`, `xvault-relayer`
7. Adds launchers to your PATH

### Post-Install

```bash
# Verify installation
xvault-miner --help
xvault --help
```

**First run:**
```bash
# Miner dashboard
xvault-miner

# Community CLI
xvault
```

### Uninstall

**Linux & macOS:**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

**Windows (PowerShell):**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
```

### Manual Install

If the one-line installer fails:

```bash
git clone https://github.com/XelisVault/xelis-vault.git ~/.xelis-vault/src
cd ~/.xelis-vault/src
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
pip install requests python-dotenv cryptography
mkdir -p ~/.xelis-vault/config
cp src/config/config.example.json ~/.xelis-vault/config/config.json
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| `python: command not found` | Install Python 3.10+ and ensure it's in PATH |
| `git: command not found` | Install git from git-scm.com |
| `Permission denied` (Linux/macOS) | Run `chmod +x ~/.local/bin/xvault*` |
| `xvault: command not found` | Restart terminal or run `source ~/.bashrc` |
| Wallet won't start | Check if port 18082/18083 is already in use |

---

## Français

### Prérequis

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **git** — [git-scm.com/downloads](https://git-scm.com/downloads/)
- **Windows :** PowerShell 5.1+ ou Invite de commandes
- **Linux/macOS :** bash, curl

### Installation en une ligne

**Linux & macOS :**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

**Windows (PowerShell) :**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

**Windows (Invite de commandes) :** téléchargez [`install.bat`](install.bat) et double-cliquez.

### Ce que fait l'installateur

1. Vérifie Python 3.10+ et git
2. Clone le dépôt dans `~/.xelis-vault/src` (ou `%USERPROFILE%\.xelis-vault\src` sous Windows)
3. Crée un environnement virtuel Python
4. Installe les dépendances : `requests`, `python-dotenv`, `cryptography`
5. Génère `config/config.json` avec les paramètres testnet par défaut
6. Installe les lanceurs : `xvault`, `xvault-miner`, `xvault-relayer`
7. Ajoute les lanceurs à votre PATH

### Post-installation

```bash
# Vérifier l'installation
xvault-miner --help
xvault --help
```

**Premier lancement :**
```bash
# Tableau de bord mineur
xvault-miner

# CLI communauté
xvault
```

### Désinstallation

**Linux & macOS :**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

**Windows (PowerShell) :**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
```

### Installation manuelle

Si l'installateur échoue :

```bash
git clone https://github.com/XelisVault/xelis-vault.git ~/.xelis-vault/src
cd ~/.xelis-vault/src
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
pip install requests python-dotenv cryptography
mkdir -p ~/.xelis-vault/config
cp src/config/config.example.json ~/.xelis-vault/config/config.json
```

### Dépannage

| Problème | Solution |
|----------|----------|
| `python: command not found` | Installez Python 3.10+ et vérifiez le PATH |
| `git: command not found` | Installez git depuis git-scm.com |
| `Permission denied` (Linux/macOS) | Exécutez `chmod +x ~/.local/bin/xvault*` |
| `xvault: command not found` | Redémarrez le terminal ou exécutez `source ~/.bashrc` |
| Le wallet ne démarre pas | Vérifiez si le port 18082/18083 est déjà utilisé |

---

## 中文

### 前置要求

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **git** — [git-scm.com/downloads](https://git-scm.com/downloads/)
- **Windows:** PowerShell 5.1+ 或命令提示符
- **Linux/macOS:** bash, curl

### 一键安装

**Linux & macOS:**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

**Windows (PowerShell):**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

**Windows (命令提示符):** 下载 [`install.bat`](install.bat) 并双击运行。

### 安装程序功能

1. 检查 Python 3.10+ 和 git
2. 克隆仓库到 `~/.xelis-vault/src` (Windows 上为 `%USERPROFILE%\.xelis-vault\src`)
3. 创建 Python 虚拟环境
4. 安装依赖：`requests`, `python-dotenv`, `cryptography`
5. 生成 `config/config.json`，使用 testnet 默认配置
6. 安装启动器：`xvault`, `xvault-miner`, `xvault-relayer`
7. 将启动器添加到 PATH

### 安装后

```bash
# 验证安装
xvault-miner --help
xvault --help
```

**首次运行：**
```bash
# 矿工仪表板
xvault-miner

# 社区 CLI
xvault
```

### 卸载

**Linux & macOS:**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

**Windows (PowerShell):**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
```

### 手动安装

如果一键安装失败：

```bash
git clone https://github.com/XelisVault/xelis-vault.git ~/.xelis-vault/src
cd ~/.xelis-vault/src
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
pip install requests python-dotenv cryptography
mkdir -p ~/.xelis-vault/config
cp src/config/config.example.json ~/.xelis-vault/config/config.json
```

### 故障排除

| 问题 | 解决方案 |
|------|----------|
| `python: command not found` | 安装 Python 3.10+ 并确保其在 PATH 中 |
| `git: command not found` | 从 git-scm.com 安装 git |
| `Permission denied` (Linux/macOS) | 运行 `chmod +x ~/.local/bin/xvault*` |
| `xvault: command not found` | 重启终端或运行 `source ~/.bashrc` |
| 钱包无法启动 | 检查端口 18082/18083 是否已被占用 |

---

## 日本語

### 前提条件

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **git** — [git-scm.com/downloads](https://git-scm.com/downloads/)
- **Windows:** PowerShell 5.1+ またはコマンドプロンプト
- **Linux/macOS:** bash, curl

### ワンラインインストール

**Linux & macOS:**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

**Windows (PowerShell):**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

**Windows (コマンドプロンプト):** [`install.bat`](install.bat) をダウンロードしてダブルクリック。

### インストーラーの機能

1. Python 3.10+ と git を確認
2. リポジトリを `~/.xelis-vault/src` (Windows では `%USERPROFILE%\.xelis-vault\src`) にクローン
3. Python 仮想環境を作成
4. 依存関係をインストール：`requests`, `python-dotenv`, `cryptography`
5. `config/config.json` を生成（testnet デフォルト設定）
6. ランチャーをインストール：`xvault`, `xvault-miner`, `xvault-relayer`
7. ランチャーを PATH に追加

### インストール後

```bash
# インストールを確認
xvault-miner --help
xvault --help
```

**初回実行：**
```bash
# マイナーダッシュボード
xvault-miner

# コミュニティ CLI
xvault
```

### アンインストール

**Linux & macOS:**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

**Windows (PowerShell):**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
```

### 手動インストール

ワンラインインストールが失敗した場合：

```bash
git clone https://github.com/XelisVault/xelis-vault.git ~/.xelis-vault/src
cd ~/.xelis-vault/src
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
pip install requests python-dotenv cryptography
mkdir -p ~/.xelis-vault/config
cp src/config/config.example.json ~/.xelis-vault/config/config.json
```

### トラブルシューティング

| 問題 | 解決策 |
|------|--------|
| `python: command not found` | Python 3.10+ をインストールし、PATH を確認 |
| `git: command not found` | git-scm.com から git をインストール |
| `Permission denied` (Linux/macOS) | `chmod +x ~/.local/bin/xvault*` を実行 |
| `xvault: command not found` | ターミナルを再起動または `source ~/.bashrc` を実行 |
| ウォレットが起動しない | ポート 18082/18083 が使用中でないか確認 |

---

## العربية

### المتطلبات الأساسية

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **git** — [git-scm.com/downloads](https://git-scm.com/downloads/)
- **Windows:** PowerShell 5.1+ أو موجه الأوامر
- **Linux/macOS:** bash, curl

### التثبيت بسطر واحد

**Linux & macOS:**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash
```

**Windows (PowerShell):**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex
```

**Windows (موجه الأوامر):** قم بتنزيل [`install.bat`](install.bat) وانقر نقرًا مزدوجًا.

### ماذا يفعل المثبت

1. يتحقق من Python 3.10+ و git
2. يستنسخ المستودع إلى `~/.xelis-vault/src` (أو `%USERPROFILE%\.xelis-vault\src` على Windows)
3. ينشئ بيئة Python افتراضية
4. يثبت التبعيات: `requests`, `python-dotenv`, `cryptography`
5. ينشئ `config/config.json` بإعدادات testnet الافتراضية
6. يثبت المشغلات: `xvault`, `xvault-miner`, `xvault-relayer`
7. يضيف المشغلات إلى PATH

### ما بعد التثبيت

```bash
# التحقق من التثبيت
xvault-miner --help
xvault --help
```

**التشغيل الأول:**
```bash
# لوحة تحكم المعدن
xvault-miner

# CLI المجتمع
xvault
```

### إلغاء التثبيت

**Linux & macOS:**
```bash
curl -fsSL https://xelisvault.github.io/xelis-vault/install | bash -s -- --uninstall
```

**Windows (PowerShell):**
```powershell
irm https://xelisvault.github.io/xelis-vault/install.ps1 | iex -Args "--uninstall"
```

### التثبيت اليدوي

إذا فشل المثبت التلقائي:

```bash
git clone https://github.com/XelisVault/xelis-vault.git ~/.xelis-vault/src
cd ~/.xelis-vault/src
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
pip install requests python-dotenv cryptography
mkdir -p ~/.xelis-vault/config
cp src/config/config.example.json ~/.xelis-vault/config/config.json
```

### استكشاف الأخطاء وإصلاحها

| المشكلة | الحل |
|---------|------|
| `python: command not found` | تثبيت Python 3.10+ والتأكد من وجوده في PATH |
| `git: command not found` | تثبيت git من git-scm.com |
| `Permission denied` (Linux/macOS) | تشغيل `chmod +x ~/.local/bin/xvault*` |
| `xvault: command not found` | إعادة تشغيل الطرفية أو تشغيل `source ~/.bashrc` |
| المحفظة لا تبدأ | التحقق من استخدام المنفذ 18082/18083 |
