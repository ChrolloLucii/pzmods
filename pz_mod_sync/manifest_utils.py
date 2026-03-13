from __future__ import annotations


def merge_workshop_items(
    existing_items: list[dict],
    incoming_items: list[dict],
) -> tuple[list[dict], int]:
    merged = [item for item in existing_items if isinstance(item, dict)]
    known = {str(item.get("publishedfileid", "")).strip() for item in merged}
    added = 0

    for item in incoming_items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("publishedfileid", "")).strip()
        if not item_id or not item_id.isdigit() or item_id in known:
            continue
        merged.append(
            {
                "publishedfileid": item_id,
                "display_name": str(item.get("display_name", f"Workshop Item {item_id}")),
            }
        )
        known.add(item_id)
        added += 1

    return merged, added
