from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.cwd() / ".carouso" / "config.json"

@dataclass
class ProviderConfig:
    provider: str = "none"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    send_images: bool = False

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key"] = "configured" if self.api_key else ""
        return data

def load_config(path: Path = CONFIG_PATH) -> ProviderConfig:
    if not path.exists():
        return ProviderConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ProviderConfig(**{key: data.get(key, value) for key, value in asdict(ProviderConfig()).items()})
    except (OSError, ValueError, TypeError):
        return ProviderConfig()

def save_config(config: ProviderConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

def complete(prompt: str, config: ProviderConfig | None = None) -> str:
    config = config or load_config()
    if not config.api_key or not config.base_url or not config.model:
        raise RuntimeError("AI belum diatur. Buka Pengaturan AI dan isi API key.")
    url = config.base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({"model": config.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.8}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise RuntimeError(f"Gagal menghubungi provider AI: {error}") from error
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Jawaban provider AI tidak dikenali.") from error

def test_connection(config: ProviderConfig) -> tuple[bool, str]:
    try:
        complete("Reply with only: ok", config)
        return True, "Koneksi berhasil."
    except RuntimeError as error:
        return False, str(error)
