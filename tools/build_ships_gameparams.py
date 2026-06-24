#!/usr/bin/env python3
"""Build a ship metadata reference from GameParams.data plus client text translations."""

from __future__ import annotations

import argparse
import json
import pickle
import re
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _install_gameparams_module() -> None:
    class GameParams(ModuleType):
        class TypeInfo(object):
            pass

        class GPData(object):
            pass

    sys.modules[GameParams.__name__] = GameParams(GameParams.__name__)


def _read_gameparams(path: Path) -> Any:
    _install_gameparams_module()
    raw = path.read_bytes()
    raw = struct.pack("B" * len(raw), *raw[::-1])
    raw = zlib.decompress(raw)
    return pickle.loads(raw, encoding="latin1")


def _unwrap_gameparams_source(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict) and "" in obj and isinstance(obj[""], dict):
        return obj[""]
    if isinstance(obj, (list, tuple)):
        for elem in obj:
            if isinstance(elem, dict) and "" in elem and isinstance(elem[""], dict):
                return elem[""]
    return {}


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    attrs = getattr(value, "__dict__", None)
    return attrs if isinstance(attrs, dict) else {}


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_ship_cache(root: Path) -> Dict[str, Any]:
    path = root / "ships_cache.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _decode_bytes(raw: bytes, preferred: str = "") -> str:
    for encoding in (preferred, "utf-8", "latin1"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("latin1", errors="ignore")


def _load_mo_catalog(path: Path) -> Dict[str, str]:
    raw = path.read_bytes()
    if len(raw) < 28:
        return {}
    magic_le = struct.unpack("<I", raw[:4])[0]
    if magic_le == 0x950412DE:
        endian = "<"
    elif magic_le == 0xDE120495:
        endian = ">"
    else:
        return {}

    _magic, _revision, nstrings, orig_tab_offset, trans_tab_offset, _hash_size, _hash_offset = struct.unpack(
        f"{endian}7I",
        raw[:28],
    )

    rows: list[tuple[bytes, bytes]] = []
    for idx in range(int(nstrings)):
        orig_len, orig_pos = struct.unpack_from(f"{endian}II", raw, int(orig_tab_offset) + idx * 8)
        trans_len, trans_pos = struct.unpack_from(f"{endian}II", raw, int(trans_tab_offset) + idx * 8)
        msgid_bytes = raw[int(orig_pos): int(orig_pos) + int(orig_len)]
        msgstr_bytes = raw[int(trans_pos): int(trans_pos) + int(trans_len)]
        rows.append((msgid_bytes, msgstr_bytes))

    charset = ""
    for msgid_bytes, msgstr_bytes in rows:
        if msgid_bytes:
            continue
        header_text = _decode_bytes(msgstr_bytes, "utf-8")
        match = re.search(r"charset=([^\s;]+)", header_text, flags=re.IGNORECASE)
        if match:
            charset = str(match.group(1) or "").strip()
        break

    catalog: Dict[str, str] = {}
    for msgid_bytes, msgstr_bytes in rows:
        if not msgid_bytes or b"\x00" in msgid_bytes:
            continue
        msgid = _decode_bytes(msgid_bytes, charset).strip()
        msgstr = _decode_bytes(msgstr_bytes, charset).strip()
        if msgid:
            catalog[msgid] = msgstr
    return catalog


def _load_text_catalogs(texts_root: Path) -> Dict[str, Dict[str, str]]:
    catalogs: Dict[str, Dict[str, str]] = {}
    if not texts_root.exists() or not texts_root.is_dir():
        return catalogs
    for locale_dir in sorted(texts_root.iterdir(), key=lambda item: item.name.lower()):
        if not locale_dir.is_dir():
            continue
        mo_path = locale_dir / "LC_MESSAGES" / "global.mo"
        if not mo_path.exists():
            continue
        try:
            messages = _load_mo_catalog(mo_path)
        except Exception:
            continue
        if messages:
            catalogs[locale_dir.name] = messages
    return catalogs


def _preferred_locale(locales: list[str]) -> str:
    if not locales:
        return ""
    english = [locale for locale in locales if locale.lower().startswith("en")]
    if english:
        return sorted(english, key=lambda item: (item.lower() != "en", item.lower()))[0]
    return sorted(locales, key=lambda item: item.lower())[0]


def _translation_for_index(catalogs: Dict[str, Dict[str, str]], ship_index: str) -> Dict[str, str]:
    if not ship_index or not catalogs:
        return {"locale": "", "short": "", "full": ""}
    locales = list(catalogs.keys())
    preferred_first = _preferred_locale(locales)
    ordered = [preferred_first] if preferred_first else []
    ordered.extend(locale for locale in sorted(locales, key=lambda item: item.lower()) if locale != preferred_first)
    for locale in ordered:
        messages = catalogs.get(locale, {})
        short_name = str(messages.get(f"IDS_{ship_index}") or "").strip()
        full_name = str(messages.get(f"IDS_{ship_index}_FULL") or "").strip()
        if short_name or full_name:
            return {
                "locale": locale,
                "short": short_name,
                "full": full_name,
            }
    return {"locale": "", "short": "", "full": ""}


def build_reference(gameparams_path: Path, texts_root: Path, ship_cache: Dict[str, Any]) -> Dict[str, Any]:
    root = _read_gameparams(gameparams_path)
    source = _unwrap_gameparams_source(root)
    catalogs = _load_text_catalogs(texts_root)

    payload: Dict[str, Any] = {
        "source_gameparams": str(gameparams_path),
        "source_texts": str(texts_root),
        "locale_count": len(catalogs),
        "ship_count": 0,
        "by_ship_id": {},
        "by_index": {},
    }
    if not isinstance(source, dict):
        return payload

    by_ship_id: Dict[str, Any] = {}
    by_index: Dict[str, Any] = {}
    for internal_name, entry in source.items():
        attrs = _as_dict(entry)
        typeinfo = _as_dict(attrs.get("typeinfo"))
        if str(typeinfo.get("type") or "").strip() != "Ship":
            continue

        ship_id = _safe_int(attrs.get("id"))
        ship_index = str(attrs.get("index") or "").strip()
        if ship_id is None or not ship_index:
            continue

        cache_entry = ship_cache.get(str(ship_id))
        if not isinstance(cache_entry, dict):
            cache_entry = {}

        translation = _translation_for_index(catalogs, ship_index)
        display_short = translation.get("short") or str(cache_entry.get("name") or "").strip()
        display_full = translation.get("full") or display_short
        display_name = (
            display_full
            or display_short
            or str(cache_entry.get("name") or "").strip()
            or str(attrs.get("name") or "").strip()
            or ship_index
        )

        tier = _safe_int(attrs.get("level"))
        if tier is None:
            tier = _safe_int(cache_entry.get("tier"))
        species = str(typeinfo.get("species") or cache_entry.get("type") or "").strip()
        nation = str(typeinfo.get("nation") or cache_entry.get("nation") or "").strip().lower()

        ship_entry = {
            "ship_id": int(ship_id),
            "id": int(ship_id),
            "index": ship_index,
            "internal_name": str(internal_name or "").strip(),
            "raw_name_token": str(attrs.get("name") or "").strip(),
            "name": display_name,
            "display_name": display_name,
            "display_name_short": display_short or display_name,
            "display_name_full": display_full or display_name,
            "translation_locale": str(translation.get("locale") or ""),
            "type": species,
            "species": species,
            "nation": nation,
            "tier": tier,
            "group": str(attrs.get("group") or "").strip(),
            "is_paper_ship": bool(attrs.get("isPaperShip")),
        }
        by_ship_id[str(ship_id)] = ship_entry
        by_index[ship_index] = ship_entry

    payload["ship_count"] = len(by_ship_id)
    payload["by_ship_id"] = dict(sorted(by_ship_id.items(), key=lambda item: int(item[0])))
    payload["by_index"] = dict(sorted(by_index.items(), key=lambda item: item[0].lower()))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ship metadata from GameParams.data and client text resources")
    parser.add_argument("--gameparams", default="", help="Path to GameParams.data (default: content/GameParams.data)")
    parser.add_argument("--texts-root", default="", help="Path to client texts root (default: content/texts)")
    parser.add_argument("--out", default="", help="Output JSON path (default: content/ships_gameparams.json)")
    args = parser.parse_args()

    root = _root_dir()
    gameparams_path = Path(args.gameparams) if args.gameparams else root / "content" / "GameParams.data"
    texts_root = Path(args.texts_root) if args.texts_root else root / "content" / "texts"
    out_path = Path(args.out) if args.out else root / "content" / "ships_gameparams.json"

    payload = build_reference(gameparams_path, texts_root, _load_ship_cache(root))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(
        f"Wrote {out_path} with {int(payload.get('ship_count', 0))} ships "
        f"using {int(payload.get('locale_count', 0))} text locales."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
