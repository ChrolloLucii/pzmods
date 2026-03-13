from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


class CollectionError(Exception):
    pass


def normalize_collection_id(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise CollectionError("Collection ID is empty.")

    if raw.isdigit():
        return raw

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"}:
        qs = parse_qs(parsed.query)
        cid = (qs.get("id") or [""])[0].strip()
        if cid.isdigit():
            return cid

    m = re.search(r"id=(\d+)", raw)
    if m:
        return m.group(1)

    raise CollectionError("Could not parse collection ID from input.")


def normalize_workshop_item_id(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise CollectionError("Workshop item ID is empty.")

    if raw.isdigit():
        return raw

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"}:
        qs = parse_qs(parsed.query)
        iid = (qs.get("id") or [""])[0].strip()
        if iid.isdigit():
            return iid

    m = re.search(r"id=(\d+)", raw)
    if m:
        return m.group(1)

    raise CollectionError("Could not parse workshop item ID from input.")


def _post_form(url: str, payload: dict[str, str], timeout: int = 30) -> dict:
    data = urlencode(payload).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "pz-mod-sync/0.1"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_collection_children(collection_id: str) -> list[str]:
    payload = {
        "collectioncount": "1",
        "publishedfileids[0]": str(collection_id),
    }
    data = _post_form("https://api.steampowered.com/ISteamRemoteStorage/GetCollectionDetails/v1/", payload)

    details = (((data or {}).get("response") or {}).get("collectiondetails") or [])
    if not details:
        raise CollectionError("Collection not found or Steam API returned no details.")

    d0 = details[0]
    if int(d0.get("result", 0)) != 1:
        raise CollectionError(f"Steam API collection result={d0.get('result')}")

    children = d0.get("children") or []
    ids: list[str] = []
    for child in children:
        pfid = str(child.get("publishedfileid", "")).strip()
        if pfid.isdigit():
            ids.append(pfid)

    if not ids:
        raise CollectionError("No workshop item IDs found in collection.")
    return ids


def fetch_workshop_item_titles(item_ids: list[str]) -> dict[str, str]:
    titles: dict[str, str] = {}
    if not item_ids:
        return titles

    chunk_size = 100
    for start in range(0, len(item_ids), chunk_size):
        chunk = item_ids[start : start + chunk_size]
        payload: dict[str, str] = {"itemcount": str(len(chunk))}
        for idx, item_id in enumerate(chunk):
            payload[f"publishedfileids[{idx}]"] = item_id

        data = _post_form("https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/", payload)
        details = (((data or {}).get("response") or {}).get("publishedfiledetails") or [])
        for d in details:
            pfid = str(d.get("publishedfileid", "")).strip()
            title = str(d.get("title", "")).strip()
            if pfid and title:
                titles[pfid] = title

    return titles
