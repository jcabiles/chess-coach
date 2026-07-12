"""Fetch recent games from the lichess / chess.com public APIs (no auth).

Network-only module: builds URLs, calls the public endpoints via httpx, and
returns raw PGN text. Parsing, dedupe, persistence, and analysis kick-off all
stay in the existing import machinery (`app.main.import_games` path) — this
module never touches storage or the engine.

Both APIs are public and keyless (no OAuth — see roadmap no-gos):
- lichess: one GET streams PGN for the user's latest games; ``clocks=true``
  embeds ``[%clk …]`` comments, which the PGN importer already parses into
  ``game_plies.clock_centis``.
- chess.com: a monthly-archive index is walked newest-first, collecting each
  month's games (JSON with an embedded ``pgn`` that carries ``%clk``) until
  ``max_games`` is reached.

Tests inject ``httpx.MockTransport`` via the ``_transport`` seam; nothing here
is reachable during the offline test suite otherwise.
"""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

LICHESS_URL = "https://lichess.org/api/games/user/{username}"
CHESSCOM_ARCHIVES_URL = "https://api.chess.com/pub/player/{username}/games/archives"

# Per-request budget. Generous because lichess streams the whole PGN body in
# one response; a hung remote is still bounded well under the UI's patience.
TIMEOUT_S = 30.0

# Hard server-side cap regardless of what the client asks for — a fetch is an
# interactive action, not a bulk-history mirror.
MAX_GAMES_CAP = 100

# Test seam: set to an httpx.MockTransport in tests. None ⇒ real network.
_transport: httpx.BaseTransport | None = None


class FetchError(Exception):
    """A fetch failed in a way the UI should explain (bad user, network down).

    ``status`` is the HTTP status to surface (404 for unknown user, 502 for
    upstream/network trouble).
    """

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT_S,
        transport=_transport,
        follow_redirects=True,
        headers={"User-Agent": "chess-coach (local training app)"},
    )


async def fetch_lichess_pgn(username: str, max_games: int) -> str:
    """Return PGN text for the user's ``max_games`` most recent games."""
    url = LICHESS_URL.format(username=username)
    params = {
        "max": min(max_games, MAX_GAMES_CAP),
        "clocks": "true",   # embed [%clk] — the whole point of API fetch
        "evals": "false",   # server evals unused; we run our own Stockfish
        "opening": "true",  # ECO/Opening headers when lichess knows them
    }
    headers = {"Accept": "application/x-chess-pgn"}
    async with _client() as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise FetchError(f"lichess unreachable: {exc}") from exc
    if resp.status_code == 404:
        raise FetchError(f"lichess user '{username}' not found", status=404)
    if resp.status_code != 200:
        raise FetchError(f"lichess returned HTTP {resp.status_code}")
    return resp.text


async def fetch_chesscom_pgn(username: str, max_games: int) -> str:
    """Return PGN text for the user's most recent chess.com games.

    Walks the monthly-archive index newest-first until ``max_games`` PGNs are
    collected (or the archives run out).
    """
    limit = min(max_games, MAX_GAMES_CAP)
    async with _client() as client:
        try:
            resp = await client.get(CHESSCOM_ARCHIVES_URL.format(username=username))
        except httpx.HTTPError as exc:
            raise FetchError(f"chess.com unreachable: {exc}") from exc
        if resp.status_code == 404:
            raise FetchError(f"chess.com user '{username}' not found", status=404)
        if resp.status_code != 200:
            raise FetchError(f"chess.com returned HTTP {resp.status_code}")
        try:
            archives = resp.json().get("archives", [])
        except json.JSONDecodeError as exc:
            raise FetchError("chess.com archive index was not JSON") from exc

        pgns: list[str] = []
        for month_url in reversed(archives):  # newest month first
            if len(pgns) >= limit:
                break
            try:
                month_resp = await client.get(month_url)
            except httpx.HTTPError as exc:
                raise FetchError(f"chess.com unreachable: {exc}") from exc
            if month_resp.status_code != 200:
                # One missing month shouldn't kill the whole fetch.
                logger.warning("fetch: chess.com month %s -> HTTP %s", month_url, month_resp.status_code)
                continue
            try:
                games = month_resp.json().get("games", [])
            except json.JSONDecodeError:
                logger.warning("fetch: chess.com month %s was not JSON", month_url)
                continue
            # Months list oldest-first within the month; take newest first.
            for game in reversed(games):
                pgn_text = game.get("pgn")
                if pgn_text:
                    pgns.append(pgn_text)
                    if len(pgns) >= limit:
                        break
    return "\n\n".join(pgns)


async def fetch_pgn(platform: str, username: str, max_games: int) -> str:
    """Dispatch to the right platform fetcher. Platform is pre-validated."""
    if platform == "lichess":
        return await fetch_lichess_pgn(username, max_games)
    if platform == "chesscom":
        return await fetch_chesscom_pgn(username, max_games)
    raise FetchError(f"unknown platform '{platform}'", status=422)
