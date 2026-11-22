"""
Roblox public API client.

Uses ONLY officially documented, publicly reachable Roblox endpoints:
  * users.roblox.com / users.roblox.com/v1/usernames/users   (resolve username → id)
  * users.roblox.com/v1/users/{id}                            (profile info)
  * friends.roblox.com/v1/users/{id}/friends/count            (friend count)
  * friends.roblox.com/v1/users/{id}/followers/count          (follower count)
  * friends.roblox.com/v1/users/{id}/followings/count         (following count)
  * thumbnails.roblox.com/v1/users/avatar                     (avatar render)
  * thumbnails.roblox.com/v1/users/avatar-headshot            (headshot)
  * games.roblox.com/v1/games                                 (game details by id list)
  * games.roblox.com/v1/games/multiget/placedetails           (place details)
  * games.roblox.com/v1/games?sortToken=...                   (popular games)
  * catalog.roblox.com/v1/catalog/items                       (catalog search)

Authentication note
-------------------
Roblox does NOT provide a public OAuth2 / "Login with Roblox" flow for third-
party desktop clients. The only officially-supported interactive login is the
roblox.com web flow (cookie-based, bound to the browser). We therefore:

  * Let the user resolve their account by Roblox USERNAME (public lookup).
  * Fetch all PUBLIC profile / avatar / catalog / game data via public APIs.
  * Never request or store passwords or auth cookies.
  * Clearly mark any field that requires an authenticated session as
    "Requires authenticated session — not available" in the UI.

This honors the spec's hard rule: "If a feature is technically unavailable
through supported Roblox integrations, explicitly report it instead of
implementing a fake substitute."
"""

from __future__ import annotations

from typing import Any

from .network import RobloxAPIError, http_get_json


# ----------------------------------------------------------------------
# Users / account
# ----------------------------------------------------------------------
def resolve_username(username: str) -> int | None:
    """Resolve a Roblox username to a user id (public endpoint)."""
    url = "https://users.roblox.com/v1/usernames/users"
    import requests
    from .network import DEFAULT_HEADERS
    try:
        resp = requests.post(
            url,
            headers={**DEFAULT_HEADERS, "Content-Type": "application/json"},
            json={"usernames": [username], "excludeBannedUsers": True},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data") or []
        if items:
            return int(items[0].get("id"))
    except Exception as exc:  # noqa: BLE001
        raise RobloxAPIError(f"Could not resolve username '{username}': {exc}")
    return None


def get_user(user_id: int) -> dict[str, Any]:
    """Return public user profile information."""
    url = f"https://users.roblox.com/v1/users/{user_id}"
    data = http_get_json(url)
    if not isinstance(data, dict) or "id" not in data:
        raise RobloxAPIError(f"Unexpected user payload for id {user_id}")
    return {
        "user_id": data["id"],
        "username": data.get("name", ""),
        "display_name": data.get("displayName", data.get("name", "")),
        "description": data.get("description", "") or "",
        "created_at": data.get("created", ""),
        "is_banned": bool(data.get("isBanned", False)),
        "profile_url": f"https://www.roblox.com/users/{data['id']}/profile",
    }


def get_user_social_counts(user_id: int) -> dict[str, int]:
    """Friends / followers / following counts."""
    out = {"friends": 0, "followers": 0, "following": 0}
    for key, url in (
        ("friends", f"https://friends.roblox.com/v1/users/{user_id}/friends/count"),
        ("followers", f"https://friends.roblox.com/v1/users/{user_id}/followers/count"),
        ("following", f"https://friends.roblox.com/v1/users/{user_id}/followings/count"),
    ):
        try:
            data = http_get_json(url, timeout=10)
            out[key] = int(data.get("count", 0))
        except Exception:
            out[key] = -1  # signal unavailable
    return out


# ----------------------------------------------------------------------
# Thumbnails — avatars & headshots
# ----------------------------------------------------------------------
def _first_image_url(thumb_resp: dict[str, Any]) -> str | None:
    data = thumb_resp.get("data") or []
    if not data:
        return None
    return data[0].get("imageUrl")


def get_avatar_full_url(user_id: int, size: str = "420x420",
                        format: str = "Png") -> str | None:
    url = ("https://thumbnails.roblox.com/v1/users/avatar"
           f"?userIds={user_id}&size={size}&format={format}&isCircular=false")
    try:
        return _first_image_url(http_get_json(url, timeout=12))
    except Exception:
        return None


def get_avatar_headshot_url(user_id: int, size: str = "420x420",
                            format: str = "Png") -> str | None:
    url = ("https://thumbnails.roblox.com/v1/users/avatar-headshot"
           f"?userIds={user_id}&size={size}&format={format}&isCircular=false")
    try:
        return _first_image_url(http_get_json(url, timeout=12))
    except Exception:
        return None


def get_avatar_render_url(user_id: int) -> str | None:
    """Full-body avatar render."""
    return get_avatar_full_url(user_id, size="420x420")


# ----------------------------------------------------------------------
# Avatar (currently worn assets) — public endpoint
# ----------------------------------------------------------------------
def get_currently_worn(user_id: int) -> dict[str, Any]:
    """Public endpoint listing currently-worn asset ids."""
    url = f"https://avatar.roblox.com/v1/users/{user_id}/currently-worn"
    try:
        data = http_get_json(url, timeout=12)
        return data or {}
    except Exception:
        return {"assets": [], "bodyColors": {}}


# ----------------------------------------------------------------------
# Games
# ----------------------------------------------------------------------
# Roblox's `games.roblox.com/v1/games?sortToken=Popularity` endpoint requires
# an authenticated session, and Roblox does not publish an officially
# supported OAuth flow for third-party desktop clients. As a result, this
# client cannot enumerate "popular" or "trending" games without an
# authenticated browser session.
#
# Per the spec's hard rule ("If a feature is technically unavailable through
# supported Roblox integrations, explicitly report it instead of
# implementing a fake substitute"), `get_games_list(sort=...)` returns an
# EMPTY list and the UI clearly explains the limitation. The user can still
# access real games via:
#   * the omni-search endpoint (search_games),
#   * direct game lookup if they know a universe id,
#   * their own locally-favorited / recently-viewed games (real data they
#     contributed themselves through search + favorite).
#
# All game DETAILS returned by get_games_details are 100% real Roblox data.
GAMES_SORT_POPULAR = "Popularity"
GAMES_SORT_TRENDING = "Trending"


def get_games_list(sort: str = GAMES_SORT_POPULAR, limit: int = 30,
                   cursor: str | None = None) -> dict[str, Any]:
    """Return a page of real Roblox games.

    The Roblox popular/trending sort endpoint requires authentication. This
    client deliberately does not impersonate a browser session, so this
    returns an empty list — the UI explains the limitation honestly.
    """
    return {"data": [], "nextPageCursor": None, "previousPageCursor": None,
            "requires_auth": True,
            "reason": ("Roblox's popular/trending games sort endpoint requires "
                       "an authenticated session, which this client does not "
                       "impersonate. Use search, or browse your own favorited / "
                       "recently-viewed games.")}


def get_games_details(universe_ids: list[int]) -> list[dict[str, Any]]:
    """Return rich live details for up to 100 universe ids at once.

    Uses the public `games.roblox.com/v1/games?universeIds=...` endpoint.
    Filters out placeholder rows Roblox returns for ids without a live cache.
    """
    if not universe_ids:
        return []
    ids = ",".join(str(i) for i in universe_ids[:100])
    url = f"https://games.roblox.com/v1/games?universeIds={ids}"
    data = http_get_json(url)
    if not isinstance(data, dict):
        raise RobloxAPIError("Unexpected game details payload")
    return [g for g in data.get("data", []) if g.get("id") and g.get("name")
            and g["name"] not in ("[TITLE UNAVAILABLE]",)]


def get_games_multiget_place_details(place_ids: list[int]) -> list[dict[str, Any]]:
    if not place_ids:
        return []
    ids = ",".join(str(i) for i in place_ids[:100])
    url = f"https://games.roblox.com/v1/games/multiget/place-details?placeIds={ids}"
    try:
        data = http_get_json(url)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def get_game_icon_url(universe_id: int, size: str = "256x256") -> str | None:
    url = ("https://thumbnails.roblox.com/v1/games/icons"
           f"?universeIds={universe_id}&size={size}&format=Png&isCircular=false")
    try:
        return _first_image_url(http_get_json(url, timeout=12))
    except Exception:
        return None


def get_game_thumbnail_url(universe_id: int, size: str = "768x432") -> str | None:
    """Return a thumbnail URL for a game.

    Roblox's dedicated `/games/game-thumbnails` GET endpoint 404s in 2025+; the
    reliable path is the `v1/batch` POST with the documented request format
    `{type: GameThumbnail, targetId, size, format}`. We request a 512x512 icon
    (a size the icons endpoint honors) as a square-tile fallback when the
    16:9 thumbnail fails, since the Games tab cards render fine with either.
    """
    import requests
    from .network import DEFAULT_HEADERS
    hdrs = {**DEFAULT_HEADERS, "Content-Type": "application/json"}
    # 1) Try a real 16:9 thumbnail via the batch endpoint.
    try:
        payload = [{"type": "GameThumbnail", "targetId": int(universe_id),
                    "size": "480x270", "format": "Png"}]
        r = requests.post("https://thumbnails.roblox.com/v1/batch",
                          headers=hdrs, json=payload, timeout=12)
        if r.status_code == 200:
            items = (r.json() or {}).get("data") or []
            if items and items[0].get("imageUrl"):
                return items[0]["imageUrl"]
    except Exception:
        pass
    # 2) Fall back to the icon (square) endpoint, which always honors 256/512.
    return get_game_icon_url(universe_id, size="512x512")


def get_game_thumbnails_batch(universe_ids: list[int]) -> dict[int, str]:
    """Fetch thumbnail URLs for many games in ONE request.

    Uses the `thumbnails.roblox.com/v1/batch` POST endpoint, which accepts up
    to 100 thumbnail requests in a single call. Returns {universe_id: url}.
    Missing/failed entries are simply omitted from the result.
    """
    import requests
    from .network import DEFAULT_HEADERS
    out: dict[int, str] = {}
    if not universe_ids:
        return out
    hdrs = {**DEFAULT_HEADERS, "Content-Type": "application/json"}
    # Deduplicate and cap at 100 (Roblox batch limit).
    uniq = list(dict.fromkeys(int(u) for u in universe_ids))[:100]
    payload = [{"type": "GameThumbnail", "targetId": uid,
                "size": "480x270", "format": "Png"} for uid in uniq]
    try:
        r = requests.post("https://thumbnails.roblox.com/v1/batch",
                          headers=hdrs, json=payload, timeout=15)
        if r.status_code != 200:
            return out
        for item in (r.json() or {}).get("data") or []:
            url = item.get("imageUrl")
            tid = item.get("targetId")
            if url and tid:
                out[int(tid)] = url
    except Exception:
        pass
    return out


def search_games(keyword: str, limit: int = 25) -> list[dict[str, Any]]:
    """Search the Roblox games catalog via the public omni-search endpoint.

    Uses the real endpoint the roblox.com web frontend calls:
        GET https://apis.roblox.com/search-api/omni-search
            ?urlLocale=en_us&searchQuery=<kw>&pageToken=
            &globalSessionId=<uuid>&sessionId=<uuid>&pageType=all

    Returns rows with {universeId, name, creator, description, rootPlaceId}.
    Real Roblox data — we never fabricate results. On failure returns [].
    """
    import uuid
    from urllib.parse import quote

    out: list[dict[str, Any]] = []
    # Roblox's omni-search returns grouped results (Games, Catalog, Users, …).
    # We only keep the Game group so the Games tab shows experiences, not hats.
    params = {
        "urlLocale": "en_us",
        "searchQuery": keyword,
        "pageToken": "",
        "globalSessionId": str(uuid.uuid4()),
        "sessionId": str(uuid.uuid4()),
        "pageType": "all",
    }
    url = "https://apis.roblox.com/search-api/omni-search"
    try:
        data = http_get_json(url, params=params, timeout=15)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    sr = data.get("searchResults")
    groups = sr if isinstance(sr, list) else []
    for group in groups:
        if not isinstance(group, dict):
            continue
        if group.get("contentGroupType") not in ("Game", "GameInstance", None):
            # Skip Catalog / Creator / Group / User rows — Games tab only.
            continue
        for inner in (group.get("contents") or []):
            if not isinstance(inner, dict):
                continue
            uid = inner.get("universeId") or inner.get("id")
            if not uid:
                continue
            # omni-search returns flat creatorName / creatorId keys (no nested object).
            creator_name = inner.get("creatorName") or inner.get("creator") or ""
            creator_id = inner.get("creatorId") or 0
            out.append({
                "universeId": int(uid),
                "rootPlaceId": inner.get("rootPlaceId"),
                "name": inner.get("name") or inner.get("displayName") or "",
                "creator": creator_name,
                "creatorId": creator_id,
                "playerCount": inner.get("playerCount"),
                "totalUpVotes": inner.get("totalUpVotes"),
                "totalDownVotes": inner.get("totalDownVotes"),
                "description": inner.get("description") or "",
                "thumbnailUrl": inner.get("thumbnailUrl"),
            })
            if len(out) >= limit:
                return out
    return out[:limit]



# ----------------------------------------------------------------------
# Catalog (avatar shop)
# ----------------------------------------------------------------------
CATALOG_CATEGORIES = {
    "All": "All",
    "Hair": "Hair",
    "Faces": "Faces",
    "Accessories": "Accessories",
    "ClassicShirts": "Classic Shirts",
    "ClassicPants": "Classic Pants",
    "LayeredClothing": "Gear",
    "Animations": "Animations",
    "BodyParts": "Body Parts",
}


def search_catalog(keyword: str = "", category: str = "All",
                   limit: int = 30, cursor: str | None = None) -> dict[str, Any]:
    """Search Roblox catalog via public endpoint.

    Endpoint: catalog.roblox.com/v1/search/items
    Only specific `limit` values are accepted (10, 28, 30, 50, 60, 100, 120).
    The search endpoint returns only {id, itemType} per item; to show names /
    prices / thumbnails we then call get_asset_details per item.
    """
    from urllib.parse import quote
    # Snap limit to a Roblox-accepted value
    allowed = {10, 28, 30, 50, 60, 100, 120}
    if limit not in allowed:
        limit = min(allowed, key=lambda v: abs(v - limit))
    params = [f"limit={limit}"]
    if keyword:
        params.append(f"keyword={quote(keyword)}")
    if category and category != "All":
        params.append(f"category={quote(category)}")
    if cursor:
        params.append(f"cursor={cursor}")
    url = "https://catalog.roblox.com/v1/search/items?" + "&".join(params)
    data = http_get_json(url)
    if not isinstance(data, dict):
        raise RobloxAPIError("Unexpected catalog payload")
    return data


def get_asset_thumbnail_url(asset_id: int, size: str = "420x420") -> str | None:
    url = ("https://thumbnails.roblox.com/v1/assets"
           f"?assetIds={asset_id}&size={size}&format=Png&isCircular=false")
    try:
        return _first_image_url(http_get_json(url, timeout=12))
    except Exception:
        return None


def get_asset_details(asset_id: int) -> dict[str, Any]:
    """Public per-asset details via the economy endpoint."""
    url = f"https://economy.roblox.com/v2/assets/{asset_id}/details"
    data = http_get_json(url, timeout=12)
    return data if isinstance(data, dict) else {}
