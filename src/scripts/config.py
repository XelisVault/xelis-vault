#!/usr/bin/env python3
"""
Shared configuration loader for xvault and xvault-miner.
"""
import json
import os
from pathlib import Path

VAULT_DIR = Path.home() / ".xelis-vault"
CONFIG_PATH = VAULT_DIR / "config" / "config.json"


class Config:
    def __init__(self):
        self.data = {
            "rpc_url": "http://127.0.0.1:18081",
            "wallet_url": "",
            "wallet_user": "wallet",
            "wallet_pass": "testpass",
            "miner_address": "",
            "miner_endpoint": "",
            "services": "both",
            "compound": False,
            "contracts": {},
        }
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                stored = json.loads(CONFIG_PATH.read_text())
                for k in self.data:
                    if k in stored:
                        self.data[k] = stored[k]
            except Exception:
                pass

    def save(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self.data, indent=2))
        try:
            os.chmod(CONFIG_PATH, 0o600)
        except Exception:
            pass

    def get(self, key, default=""):
        return self.data.get(key, default)

    def reset(self):
        defaults = {
            "rpc_url": "http://127.0.0.1:18081",
            "wallet_url": "",
            "wallet_user": "wallet",
            "wallet_pass": "testpass",
            "miner_address": "",
            "miner_endpoint": "",
            "services": "both",
            "compound": False,
            "contracts": {},
        }
        self.data = defaults
        self.save()

    @property
    def contracts(self):
        return self.data.get("contracts", {})
