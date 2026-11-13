"""Bounded Riot access and deterministic champion statistics."""
import os
import time
from collections import defaultdict
from threading import Lock
from urllib.parse import quote

import requests

from app.settings import positive_int


class RiotError(Exception):
    pass


# Shared across requests in this process. Never sleep inside an agent request.
_request_lock = Lock()
_blocked_until = 0.0


class RiotTools:
    def __init__(self):
        self.api_key = os.getenv("RIOT_API_KEY", "")
        self.max_matches = min(100, positive_int("RIOT_MAX_MATCHES", 20))
        self.remaining = positive_int("RIOT_REQUEST_BUDGET", 120)
        self.timeout = positive_int("RIOT_TIMEOUT_SECONDS", 10)
        self.cache = {}

    def _get(self, region: str, path: str, params=None):
        global _blocked_until
        if region not in {"europe", "americas", "asia", "sea"}:
            raise RiotError("Region must be europe, americas, asia or sea.")
        if not self.api_key:
            raise RiotError("RIOT_API_KEY is missing. Configure it on the server, never in chat.")
        cache_key = (region, path, tuple(sorted((params or {}).items())))
        if cache_key in self.cache:
            return self.cache[cache_key]
        with _request_lock:
            wait = max(0, int(_blocked_until - time.monotonic() + 1))
            if wait:
                raise RiotError(f"Riot rate limit: retry after {wait} seconds. Do not retry now.")
            if self.remaining <= 0:
                raise RiotError("Riot request budget exhausted for this turn.")
            self.remaining -= 1
            try:
                response = requests.get(
                    f"https://{region}.api.riotgames.com{path}", params=params,
                    headers={"X-Riot-Token": self.api_key}, timeout=self.timeout,
                    allow_redirects=False,
                )
            except requests.RequestException:
                raise RiotError("Riot connection failed or timed out.") from None
            if response.status_code == 429:
                try:
                    delay = max(1, int(response.headers.get("Retry-After", "120")))
                except ValueError:
                    delay = 120
                _blocked_until = time.monotonic() + delay
                raise RiotError(f"Riot rate limit: retry after {delay} seconds. Do not retry now.")
            if response.status_code != 200:
                description = {401: "Missing or invalid API key", 403: "API key expired, forbidden or invalid route",
                               404: "Account or match not found"}.get(response.status_code, "Riot request failed")
                raise RiotError(f"{description} (HTTP {response.status_code}).")
            try:
                data = response.json()
            except ValueError:
                raise RiotError("Riot returned invalid JSON.") from None
        self.cache[cache_key] = data
        return data

    def riot_account(self, game_name: str, tag_line: str, region: str = "europe") -> dict:
        """Resolve Riot ID (game name and tag without #) to PUUID.

        Ask for Riot ID and region when unknown. Regional routes: europe,
        americas, asia, sea. Never ask the user to paste an API key into chat.
        """
        try:
            data = self._get(region, f"/riot/account/v1/accounts/by-riot-id/{quote(game_name, safe='')}/{quote(tag_line, safe='')}")
            return {key: data.get(key) for key in ("puuid", "gameName", "tagLine")}
        except RiotError as error:
            return {"error": str(error)}

    def _match_ids(self, puuid, region, count, start, queue):
        if not 1 <= count <= self.max_matches or not 0 <= start <= 10000:
            raise RiotError(f"count must be 1..{self.max_matches}; start must be 0..10000.")
        if queue not in (420, 440):
            raise RiotError("Supported queues: 420 ranked solo/duo, 440 ranked flex.")
        return self._get(region, f"/lol/match/v5/matches/by-puuid/{quote(puuid, safe='')}/ids",
                         {"start": start, "count": count, "queue": queue})

    def riot_match_history(self, puuid: str, region: str = "europe", count: int = 10,
                           start: int = 0, queue: int = 420) -> dict:
        """Get ranked match IDs. queue: 420 solo/duo or 440 flex.

        Use start for older pages. A full page does not guarantee more history.
        """
        try:
            ids = self._match_ids(puuid, region, count, start, queue)
            return {"match_ids": ids, "next_start": start + len(ids), "page_full": len(ids) == count}
        except RiotError as error:
            return {"error": str(error)}

    def riot_analyze_champions(self, puuid: str, region: str = "europe", count: int = 10,
                               start: int = 0, queue: int = 420) -> dict:
        """Analyze recent ranked matches by champion AND role, using Python statistics.

        Resolve PUUID with riot_account first. count defaults to 10; start pages
        into older matches. queue: 420 solo/duo, 440 flex. Includes patches and
        sample counts. This is personal history, NOT current meta or causal proof.
        Never claim a small-sample win rate proves a champion is best.
        """
        try:
            ids = self._match_ids(puuid, region, count, start, queue)
        except RiotError as error:
            return {"error": str(error)}
        rows, failures, skipped = [], [], 0
        for index, match_id in enumerate(ids):
            try:
                match = self._get(region, f"/lol/match/v5/matches/{quote(match_id, safe='')}")
            except RiotError as error:
                failures.append({"match_id": match_id, "error": str(error)})
                break
            info = match.get("info", {})
            player = next((p for p in info.get("participants", []) if p.get("puuid") == puuid), None)
            duration = info.get("gameDuration", 0)
            if not player or duration <= 0 or info.get("queueId") != queue or player.get("gameEndedInEarlySurrender"):
                skipped += 1
                continue
            rows.append({"match_id": match_id, "champion": player["championName"],
                         "role": player.get("teamPosition") or "UNKNOWN",
                         "patch": ".".join(info.get("gameVersion", "unknown").split(".")[:2]),
                         "win": bool(player.get("win")), "kills": player.get("kills", 0),
                         "deaths": player.get("deaths", 0), "assists": player.get("assists", 0),
                         "cs_per_min": (player.get("totalMinionsKilled", 0) + player.get("neutralMinionsKilled", 0)) / (duration / 60),
                         "damage_per_min": player.get("totalDamageDealtToChampions", 0) / (duration / 60)})
        groups = defaultdict(list)
        for row in rows:
            groups[(row["champion"], row["role"])].append(row)
        summaries = []
        for (champion, role), games in groups.items():
            n = len(games)
            summaries.append({"champion": champion, "role": role, "games": n,
                              "wins": sum(g["win"] for g in games),
                              "win_rate": round(sum(g["win"] for g in games) / n, 3),
                              "patches": sorted({g["patch"] for g in games}),
                              **{f"avg_{key}": round(sum(g[key] for g in games) / n, 2)
                                 for key in ("kills", "deaths", "assists", "cs_per_min", "damage_per_min")}})
        return {"queue": queue, "requested": count, "fetched_ids": len(ids), "analyzed": len(rows),
                "skipped": skipped, "partial": bool(failures), "errors": failures,
                "next_start": start + (index if failures else len(ids)) if ids else start,
                "champions": sorted(summaries, key=lambda x: (-x["games"], x["champion"], x["role"])),
                "matches": rows,
                "limitations": "Personal ranked sample, grouped by role; remakes excluded. Patches may differ. No global meta, rank adjustment or draft context. State sample size and uncertainty; ask about goals before recommending a champion pool."}
