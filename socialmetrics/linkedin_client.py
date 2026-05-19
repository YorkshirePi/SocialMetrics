"""Minimal LinkedIn Community Management API client (stdlib only).

This pulls organization posts and their engagement counts so the output can be
fed straight into :mod:`socialmetrics.analyze`.

Requirements that are NOT satisfiable inside this container (documented here so
the operator knows exactly what to arrange before running this):

* **Network egress to ``api.linkedin.com``.** The build/dev sandbox blocks it
  ("Host not in allowlist"); run this from a host that can reach LinkedIn.
* **A 3-legged OAuth member access token** for someone who is an *admin* of
  both the Vision RT and SGRT Community pages, with scopes
  ``r_organization_social`` (and ``rw_organization_admin`` for the page).
  Client id + secret alone (2-legged ``client_credentials``) do **not** grant
  organization social scopes.
* **Marketing Developer Platform approval** on the app for the Community
  Management API product.

Engagement-data caveats baked into the analysis:

* ``/socialActions/{urn}`` returns like and comment *counts* per post. There is
  no first-class public per-post **repost** count; ``reposts`` is best-effort
  from the posts payload and may be 0 if absent.
* Like/comment *actor* endpoints return member URNs, never the actor's
  employer. The "exclude Vision RT employees" pass therefore cannot be driven
  by the API alone — it needs an employee roster/enrichment supplied
  separately. ``export_interactions`` emits rows with an empty
  ``actor_employer`` for exactly this reason.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import urllib.parse
import urllib.request

_API_BASE = "https://api.linkedin.com"
_DEFAULT_VERSION = "202401"  # LinkedIn-Version header (YYYYMM)


class LinkedInError(RuntimeError):
    pass


class LinkedInClient:
    def __init__(self, access_token: str, api_version: str = _DEFAULT_VERSION,
                 timeout: int = 30):
        if not access_token:
            raise LinkedInError("A 3-legged member access token is required.")
        self._token = access_token
        self._version = api_version
        self._timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{_API_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params, safe=":(),")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "LinkedIn-Version": self._version,
            "X-Restli-Protocol-Version": "2.0.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            body = exc.read().decode("utf-8", "replace")
            raise LinkedInError(f"HTTP {exc.code} for {path}: {body}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise LinkedInError(
                f"Network error reaching LinkedIn for {path}: {exc}. "
                "Confirm egress to api.linkedin.com is allowed."
            ) from exc

    def iter_org_posts(self, org_urn: str):
        """Yield raw post objects authored by ``org_urn`` (paginated)."""
        start = 0
        page = 100
        while True:
            payload = self._get("/rest/posts", {
                "q": "author",
                "author": org_urn,
                "count": page,
                "start": start,
            })
            elements = payload.get("elements", [])
            yield from elements
            if len(elements) < page:
                return
            start += page

    def post_engagement(self, post_urn: str) -> dict:
        """Return {'likes': int, 'comments': int} for a post URN."""
        data = self._get(f"/rest/socialActions/{urllib.parse.quote(post_urn)}")
        likes = data.get("likesSummary", {}).get("totalLikes", 0)
        comments = data.get("commentsSummary", {}).get(
            "aggregatedTotalComments",
            data.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
        )
        return {"likes": int(likes), "comments": int(comments)}

    @staticmethod
    def _created_date(post: dict) -> _dt.date | None:
        ts = post.get("createdAt") or post.get("publishedAt")
        if not ts:
            return None
        return _dt.datetime.fromtimestamp(ts / 1000, _dt.timezone.utc).date()

    def export_posts(self, channels: dict[str, str], year: int, month: int,
                      out_path: str) -> int:
        """Write a posts CSV consumable by analyze.load_posts.

        ``channels`` maps a human channel label -> organization URN.
        Returns the number of rows written.
        """
        rows = 0
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["channel", "post_id", "posted_at", "likes",
                        "comments", "reposts"])
            for label, org_urn in channels.items():
                for post in self.iter_org_posts(org_urn):
                    d = self._created_date(post)
                    if not d or d.year != year or d.month != month:
                        continue
                    post_urn = post.get("id") or post.get("urn", "")
                    eng = self.post_engagement(post_urn)
                    reposts = (
                        post.get("reshareCount")
                        or post.get("totalShareStatistics", {}).get("shareCount")
                        or 0
                    )
                    w.writerow([label, post_urn, d.isoformat(),
                                eng["likes"], eng["comments"], int(reposts)])
                    rows += 1
        return rows
