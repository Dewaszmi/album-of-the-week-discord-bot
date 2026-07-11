def artist_name(artist) -> str:
    if isinstance(artist, dict):
        return artist.get("name", "")
    return artist or ""


def extract_cover_image(images) -> str:
    for image in reversed(images or []):
        if image.get("#text"):
            return image["#text"]
    return ""


def album_data_to_entry(data: dict, user_name: str = "", user_id=None) -> dict:
    return {
        "artist": artist_name(data.get("artist")),
        "title": data.get("name", ""),
        "url": data.get("url", ""),
        "image": extract_cover_image(data.get("image")),
        "user_name": user_name.strip() or "Web UI",
        "user_id": user_id,
    }


def album_data_to_preview(data: dict) -> dict:
    entry = album_data_to_entry(data)
    return {
        "artist": entry["artist"],
        "title": entry["title"],
        "url": entry["url"],
        "image": entry["image"],
    }
