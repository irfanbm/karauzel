from __future__ import annotations

import ipaddress
import json
import re
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .design import clean_design
from .structures import CTA_TYPES, MAX_SLIDES, MIN_SLIDES, ROLES, STRUCTURES, outline

PROJECTS_DIR = Path.cwd() / "projects"
MAX_IMAGE_BYTES = 15 * 1024 * 1024
IMAGE_TYPES = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"GIF87a": ".gif",
    b"GIF89a": ".gif",
}
_ID = re.compile(r"^[a-z0-9-]{1,80}$")
_FILE = re.compile(r"^[a-z0-9-]{1,80}\.(jpg|png|gif|webp)$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40].strip("-") or "carousel"


def project_dir(project_id: str) -> Path:
    if not _ID.match(project_id or ""):
        raise ValueError("invalid project id")
    return PROJECTS_DIR / project_id


def _clean_rich(value: Any, limit: int) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    clean = []
    for item in value[:80]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", ""))[:limit]
        if not text:
            continue
        clean.append({"text": text, "bold": "1" if str(item.get("bold", "0")).lower() in ("1", "true", "yes") else "0", "italic": "1" if str(item.get("italic", "0")).lower() in ("1", "true", "yes") else "0", "underline": "1" if str(item.get("underline", "0")).lower() in ("1", "true", "yes") else "0", "important": str(item.get("important", ""))[:20], "font": "" if str(item.get("font", "")) == "system" else str(item.get("font", ""))[:40]})
    return clean


def new_slide(role: str) -> dict[str, Any]:
    return {
        "id": secrets.token_hex(4),
        "role": role if role in ROLES else "point",
        "headline": "",
        "headline_options": [],
        "headline_rich": [],
        "body": "",
        "body_rich": [],
        "bullets": [],
        "image": None,
        "images": [],
        "locked": False,
        "notes": "",
    }


def default_brief() -> dict[str, Any]:
    return {
        "topic": "",
        "goal": "educate",
        "audience": "",
        "language": "Bahasa Indonesia",
        "tone": "friendly",
        "slides": 6,
        "structure": "auto",
        "source": "",
        "handle": "",
        "cta_type": "save",
        "cta_detail": "",
    }


def _clean_brief(data: dict[str, Any]) -> dict[str, Any]:
    brief = default_brief()
    for key, default in brief.items():
        if key in data and data[key] is not None:
            brief[key] = data[key] if isinstance(default, int) else str(data[key]).strip()
    try:
        brief["slides"] = max(MIN_SLIDES, min(MAX_SLIDES, int(brief["slides"])))
    except (TypeError, ValueError):
        brief["slides"] = 6
    if brief["structure"] not in STRUCTURES:
        brief["structure"] = "auto"
    if brief["cta_type"] not in CTA_TYPES:
        brief["cta_type"] = "save"
    brief["source"] = brief["source"][:12000]
    return brief


def _clean_slide(data: dict[str, Any]) -> dict[str, Any]:
    slide = new_slide(str(data.get("role", "point")))
    if re.fullmatch(r"[a-f0-9]{8}", str(data.get("id", ""))):
        slide["id"] = data["id"]
    slide["headline"] = str(data.get("headline", ""))[:200]
    slide["headline_rich"] = _clean_rich(data.get("headline_rich"), 200)
    options = data.get("headline_options", [])
    slide["headline_options"] = [str(item)[:200] for item in options if str(item).strip()][:3] if isinstance(options, list) else []
    slide["body"] = str(data.get("body", ""))[:600]
    slide["body_rich"] = _clean_rich(data.get("body_rich"), 600)
    bullets = data.get("bullets") or []
    slide["bullets"] = [str(item)[:160] for item in bullets if str(item).strip()][:6] if isinstance(bullets, list) else []
    image = data.get("image")
    images = data.get("images")
    clean_images = [item for item in images if isinstance(item, str) and _FILE.match(item)][:4] if isinstance(images, list) else []
    if isinstance(image, str) and _FILE.match(image) and image not in clean_images:
        clean_images.insert(0, image)
    slide["images"] = clean_images[:4]
    slide["image"] = clean_images[0] if clean_images else None
    slide["locked"] = bool(data.get("locked"))
    slide["notes"] = str(data.get("notes", ""))[:300]
    return slide


def create(brief: dict[str, Any] | None = None) -> dict[str, Any]:
    clean = _clean_brief(brief or {})
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    base = f"{time.strftime('%Y%m%d')}-{_slugify(clean['topic'] or 'carousel')}"
    project_id = base
    while (PROJECTS_DIR / project_id).exists():
        project_id = f"{base}-{secrets.token_hex(2)}"
    project = {
        "id": project_id,
        "version": 1,
        "created": _now(),
        "updated": _now(),
        "brief": clean,
        "slides": [new_slide(role) for role in outline(clean["structure"], clean["slides"])],
    }
    save(project)
    return project


def save(project: dict[str, Any]) -> dict[str, Any]:
    folder = project_dir(project["id"])
    folder.mkdir(parents=True, exist_ok=True)
    clean = {
        "id": project["id"],
        "version": 1,
        "created": project.get("created") or _now(),
        "updated": _now(),
        "brief": _clean_brief(project.get("brief") or {}),
        "slides": [_clean_slide(slide) for slide in (project.get("slides") or [])][:MAX_SLIDES],
        "design": clean_design(project.get("design")),
    }
    target = folder / "project.json"
    temp = folder / "project.json.tmp"
    temp.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(target)
    return clean


def load(project_id: str) -> dict[str, Any]:
    path = project_dir(project_id) / "project.json"
    if not path.exists():
        raise FileNotFoundError(project_id)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def list_projects() -> list[dict[str, str]]:
    if not PROJECTS_DIR.exists():
        return []
    items = []
    for path in PROJECTS_DIR.glob("*/project.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            items.append({"id": data["id"], "topic": data["brief"].get("topic", ""), "updated": data.get("updated", ""), "status": data.get("status", "Brief")})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(items, key=lambda item: item["updated"], reverse=True)


def _detect(data: bytes) -> str:
    for magic, ext in IMAGE_TYPES.items():
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("File harus berupa gambar JPG, PNG, GIF, atau WebP.")


def store_image(project_id: str, data: bytes) -> str:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Ukuran gambar lebih dari 15 MB.")
    if not data:
        raise ValueError("File kosong.")
    ext = _detect(data)
    folder = project_dir(project_id) / "images"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"img-{secrets.token_hex(5)}{ext}"
    (folder / name).write_bytes(data)
    return name


def _public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as error:
        raise ValueError(f"Alamat {host} tidak ditemukan.") from error
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("URL mengarah ke alamat jaringan lokal, tidak diizinkan.")


def fetch_image(project_id: str, url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Masukkan URL gambar lengkap yang diawali http:// atau https://.")
    _public_host(parsed.hostname)
    request = urllib.request.Request(url, headers={"User-Agent": "Carouso/2.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise ValueError(f"Gambar tidak bisa diunduh: {error}") from error
    return store_image(project_id, data)


def image_path(project_id: str, name: str) -> Path:
    if not _FILE.match(name or ""):
        raise ValueError("invalid image name")
    return project_dir(project_id) / "images" / name
