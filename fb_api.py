import json
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional

GRAPH_VER = "v24.0"


def _graph(url: str) -> str:
    return f"https://graph.facebook.com/{GRAPH_VER}/{url.lstrip('/')}"


def _json_or_text(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def publish_photos_unpublished(
    page_id: str,
    token: str,
    photo_paths: List[Path],
    limit: int = 10
) -> List[str]:
    """
    Upload photos as unpublished to get media_fbid IDs.
    Returns list of media IDs.
    """
    media_ids: List[str] = []
    for p in photo_paths[:limit]:
        url = _graph(f"{page_id}/photos")
        with open(p, "rb") as f:
            resp = requests.post(
                url,
                params={"access_token": token},
                data={"published": "false"},
                files={"source": f},
                timeout=120,
            )

        payload = _json_or_text(resp)
        if not resp.ok:
            raise RuntimeError(f"FB upload photo failed {resp.status_code}: {payload}")

        mid = payload.get("id")
        if not mid:
            raise RuntimeError(f"FB upload photo missing id: {payload}")

        media_ids.append(mid)

    return media_ids


def create_post_with_attached_media(
    page_id: str,
    token: str,
    message: str,
    media_ids: List[str]
) -> str:
    """
    Create a page feed post with attached media.
    Returns post_id (string) for backward compatibility.
    """
    url = _graph(f"{page_id}/feed")
    data: Dict[str, str] = {"message": message}

    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})

    resp = requests.post(url, params={"access_token": token}, data=data, timeout=120)
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB create post failed {resp.status_code}: {payload}")

    post_id = payload.get("id")
    if not post_id:
        raise RuntimeError(f"FB create post missing id: {payload}")

    return post_id


def create_post_with_attached_media_full(
    page_id: str,
    token: str,
    message: str,
    media_ids: List[str]
) -> Dict[str, Any]:
    """
    Same as create_post_with_attached_media but returns full Meta payload.
    """
    url = _graph(f"{page_id}/feed")
    data: Dict[str, str] = {"message": message}

    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})

    resp = requests.post(url, params={"access_token": token}, data=data, timeout=120)
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB create post failed {resp.status_code}: {payload}")

    if not payload.get("id"):
        raise RuntimeError(f"FB create post missing id: {payload}")

    return payload


def update_post_text(post_id: str, token: str, message: str) -> Dict[str, Any]:
    """
    Update an existing post's message.
    Returns full Meta payload (so you can log it).
    """
    url = _graph(post_id)
    resp = requests.post(
        url,
        params={"access_token": token},
        data={"message": message},
        timeout=60,
    )
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB update text failed {resp.status_code}: {payload}")

    return payload


def delete_post(post_id: str, token: str) -> bool:
    """
    Supprime un post Facebook.
    
    Args:
        post_id: ID du post à supprimer
        token: Token d'accès de la page
    
    Returns:
        True si suppression réussie, False sinon.
    """
    url = _graph(post_id)
    resp = requests.delete(
        url,
        params={"access_token": token},
        timeout=60,
    )
    payload = _json_or_text(resp)

    if not resp.ok:
        print(f"[FB DELETE] Failed {resp.status_code}: {payload}")
        return False

    return payload.get("success", False)


def comment_on_post(post_id: str, token: str, message: str) -> str:
    """
    Create a comment on a post. Returns comment_id (string).
    """
    url = _graph(f"{post_id}/comments")
    resp = requests.post(url, params={"access_token": token}, data={"message": message}, timeout=60)
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB comment failed {resp.status_code}: {payload}")

    return payload.get("id", "")


def comment_photo(post_id: str, token: str, attachment_id: str, message: str = "") -> str:
    """
    Comment with a photo attachment (attachment_id = media_fbid). Returns comment_id.
    """
    url = _graph(f"{post_id}/comments")
    data: Dict[str, str] = {"attachment_id": attachment_id}
    if message:
        data["message"] = message

    resp = requests.post(url, params={"access_token": token}, data=data, timeout=60)
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB comment photo failed {resp.status_code}: {payload}")

    return payload.get("id", "")


def publish_photos_as_comment_batch(
    page_id: str, 
    token: str, 
    post_id: str, 
    photo_paths: List[Path],
    message: str = "📸 Suite des photos 👇"
) -> None:
    """
    Publie les photos extra en commentaires (pas en posts).
    
    Args:
        page_id: ID de la page Facebook
        token: Token d'accès
        post_id: ID du post existant
        photo_paths: Liste des chemins vers les photos
        message: Message d'introduction (défaut: "📸 Suite des photos 👇")
    """
    if not photo_paths:
        return

    # Commentaire d'introduction (best-effort)
    try:
        comment_on_post(post_id, token, message)
    except Exception:
        pass

    # Upload en unpublished, puis attache chaque photo au post via commentaire
    for p in photo_paths:
        url = _graph(f"{page_id}/photos")
        with open(p, "rb") as f:
            resp = requests.post(
                url,
                params={"access_token": token},
                data={"published": "false"},
                files={"source": f},
                timeout=120,
            )

        payload = _json_or_text(resp)
        if not resp.ok:
            raise RuntimeError(f"FB upload extra photo failed {resp.status_code}: {payload}")

        mid = payload.get("id")
        if not mid:
            raise RuntimeError(f"FB upload extra photo missing id: {payload}")

        # Attache la photo comme commentaire (PAS un post)
        comment_photo(post_id, token, attachment_id=mid)


def fetch_fb_post_message(post_id: str, token: str) -> str:
    """
    Fetch current post message (proof after update).
    """
    url = _graph(post_id)
    resp = requests.get(
        url,
        params={"access_token": token, "fields": "message"},
        timeout=30,
    )
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB fetch post failed {resp.status_code}: {payload}")

    return (payload or {}).get("message") or ""


# Alias (si tu veux un nom plus court)
def fetch_post_message(post_id: str, token: str) -> str:
    return fetch_fb_post_message(post_id, token)



def fetch_page_posts(page_id: str, token: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Récupère les posts publiés sur la page FB.
    Retourne une liste de {id, message, created_time, attachments}.
    Pagine automatiquement jusqu'à `limit`.
    """
    all_posts: List[Dict[str, Any]] = []
    url = _graph(f"{page_id}/feed")
    params = {
        "access_token": token,
        "fields": "id,message,created_time,attachments{media_type,subattachments}",
        "limit": min(limit, 100),
    }

    while len(all_posts) < limit:
        try:
            resp = requests.get(url, params=params, timeout=30)
            if not resp.ok:
                print(f"[FB FEED] Error {resp.status_code}: {_json_or_text(resp)}")
                break
            data = resp.json()
        except Exception as e:
            print(f"[FB FEED] Request failed: {e}")
            break

        posts = data.get("data") or []
        if not posts:
            break

        all_posts.extend(posts)

        # Pagination
        paging = data.get("paging", {})
        next_url = paging.get("next")
        if not next_url:
            break
        url = next_url
        params = {}  # next_url contient déjà les params

    return all_posts[:limit]


def count_post_photos(post: Dict[str, Any]) -> int:
    """Compte le nombre de photos dans un post FB."""
    attachments = post.get("attachments", {}).get("data", [])
    count = 0
    for att in attachments:
        if att.get("media_type") == "photo":
            count += 1
        # Subattachments (album)
        subs = att.get("subattachments", {}).get("data", [])
        count += len(subs)
    return max(count, 1) if attachments else 0
