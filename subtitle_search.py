"""
OpenSubtitles.com REST client (API v1) for searching and downloading subtitles.
Needs a free API key; downloading also needs an OpenSubtitles account.
"""

import json
import os
import struct
import urllib.error
import urllib.parse
import urllib.request

from liquid_theme import APP_NAME, APP_VERSION

API = "https://api.opensubtitles.com/api/v1"


class SubtitleError(Exception):
    pass


def movie_hash(path: str) -> str:
    """OpenSubtitles hash: file size plus the 64-bit word sums of the first and last 64 KiB."""
    chunk = 65536
    size = os.path.getsize(path)
    if size < chunk * 2:
        return ""
    h = size
    with open(path, "rb") as f:
        for offset in (0, size - chunk):
            f.seek(offset)
            for (word,) in struct.iter_unpack("<Q", f.read(chunk)):
                h = (h + word) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


class OpenSubtitlesClient:
    def __init__(self, api_key: str, username: str = "", password: str = ""):
        if not api_key:
            raise SubtitleError("Add meg az OpenSubtitles API-kulcsot a Beállítások → Távvezérlés és online lapon.")
        self.api_key, self.username, self.password = api_key, username, password
        self.token = None

    def _request(self, method: str, path: str, params=None, body=None) -> dict:
        url = f"{API}/{path}"
        if params:
            # The API redirects unless parameters are lower-case and sorted
            url += "?" + urllib.parse.urlencode(sorted((k.lower(), str(v).lower()) for k, v in params.items() if v))
        headers = {"Api-Key": self.api_key, "User-Agent": f"{APP_NAME} v{APP_VERSION}",
                   "Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8")).get("message", "")
            except (ValueError, AttributeError):
                detail = ""
            raise SubtitleError(f"OpenSubtitles hiba ({e.code}){': ' + detail if detail else ''}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SubtitleError(f"Nem érhető el az OpenSubtitles: {e}") from e

    def search(self, query: str, languages: str, path: str = "") -> list:
        params = {"languages": languages, "query": query}
        if path and os.path.isfile(path):
            params["moviehash"] = movie_hash(path)
        results = []
        for entry in self._request("GET", "subtitles", params).get("data", []):
            attrs = entry.get("attributes", {})
            files = attrs.get("files") or []
            if not files:
                continue
            feature = attrs.get("feature_details") or {}
            results.append({
                "file_id": files[0].get("file_id"),
                "file_name": files[0].get("file_name") or "",
                "language": attrs.get("language") or "",
                "release": attrs.get("release") or feature.get("title") or "",
                "downloads": attrs.get("download_count") or 0,
                "hash_match": bool(attrs.get("moviehash_match")),
            })
        results.sort(key=lambda r: (not r["hash_match"], -r["downloads"]))
        return results

    def download(self, file_id: int, target_dir: str, base_name: str) -> str:
        if not self.token and self.username:
            self.token = self._request("POST", "login", body={"username": self.username,
                                                             "password": self.password}).get("token")
        info = self._request("POST", "download", body={"file_id": file_id})
        link = info.get("link")
        if not link:
            raise SubtitleError(info.get("message") or "A letöltési korlát elfogyott, vagy bejelentkezés szükséges.")
        ext = os.path.splitext(info.get("file_name") or "")[1] or ".srt"
        target = os.path.join(target_dir, base_name + ext)
        try:
            with urllib.request.urlopen(link, timeout=30) as resp, open(target, "wb") as f:
                f.write(resp.read())
        except (urllib.error.URLError, OSError) as e:
            raise SubtitleError(f"A felirat nem menthető: {e}") from e
        return target
