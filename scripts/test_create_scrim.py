"""Create a Spire Scrims scrim with lobbies and players via the REST API.

Usage:
    python3 scripts/test_create_scrim.py

Environment (read from scripts/.env if present; shell variables take precedence):
    SCRIMS_API_KEY   Production API key (required).

This script creates real production data. It prints a delete command when it
finishes so the test scrim can be removed.

Configuration lives in the constants below:
    SCRIM_NAME / SCRIM_TYPE / IS_PRIVATE   the scrim itself
    POINT_SYSTEM_NAME / MAP_LINEUP_NAME    optional attachments, resolved by name
    LOBBY_ROSTERS                          one list of player names per lobby
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import requests
from dotenv import load_dotenv

_ = load_dotenv(Path(__file__).parent / ".env")

# --- Configuration ---------------------------------------------------------

SCRIM_NAME = "API test scrim"
SCRIM_TYPE = "Solos"  # "Solos" | "Duos" | "Trios"
IS_PRIVATE = False

POINT_SYSTEM_NAME = "Points 4.0 (Newest)"
MAP_LINEUP_NAME = "FSD > SE > HSD > SR > DS > FSN"

LOBBY_ROSTERS = [
    ["1stGlitch", "A penguin", "Almejitaz"],
    ["Alowne", "ihelane", "orenji"],
]

# ---------------------------------------------------------------------------

REQUEST_TIMEOUT_SECONDS = 30


class ApiError(Exception):
    """A request failed or the API returned an unexpected response."""


@dataclass(frozen=True)
class NamedResource:
    """An API resource represented by an ID and display name."""

    id: str
    name: str


@dataclass(frozen=True)
class CreatedLobby:
    """The fields returned after creating a lobby."""

    id: str
    number: int


def require_string(payload: dict[str, object], key: str) -> str:
    """Read a required string field from a response object."""
    value = payload.get(key)
    if not isinstance(value, str):
        raise ApiError(f"API response field '{key}' must be a string")
    return value


def require_integer(payload: dict[str, object], key: str) -> int:
    """Read a required integer field from a response object."""
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError(f"API response field '{key}' must be an integer")
    return value


def require_object(payload: dict[str, object], key: str) -> dict[str, object]:
    """Read a required JSON object field from a response object."""
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ApiError(f"API response field '{key}' must be an object")
    return cast(dict[str, object], value)


def require_string_list(payload: dict[str, object], key: str) -> list[str]:
    """Read a required list of strings from a response object."""
    value = payload.get(key)
    if not isinstance(value, list):
        raise ApiError(f"API response field '{key}' must be a list")

    values = cast(list[object], value)
    if not all(isinstance(item, str) for item in values):
        raise ApiError(f"API response field '{key}' must contain only strings")
    return cast(list[str], values)


def require_named_resources(
    payload: dict[str, object], key: str
) -> list[NamedResource]:
    """Read a required list of named resources from a response object."""
    value = payload.get(key)
    if not isinstance(value, list):
        raise ApiError(f"API response field '{key}' must be a list")

    resources: list[NamedResource] = []
    for value_item in cast(list[object], value):
        if not isinstance(value_item, dict):
            raise ApiError(f"API response field '{key}' contains an invalid item")
        item = cast(dict[str, object], value_item)
        resources.append(
            NamedResource(
                id=require_string(item, "id"),
                name=require_string(item, "name"),
            )
        )
    return resources


class ScrimsClient:
    """Minimal client for the Spire Scrims REST API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.session: requests.Session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"

    @staticmethod
    def _decode_object(response: requests.Response) -> dict[str, object]:
        try:
            decoded = cast(object, response.json())
        except ValueError as error:
            raise ApiError("API response was not valid JSON") from error

        if not isinstance(decoded, dict):
            raise ApiError("API response must be a JSON object")
        return cast(dict[str, object], decoded)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        response = self.session.request(
            method,
            f"{self.base_url}/api/{path}",
            params=params,
            json=json_body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        if not response.ok:
            try:
                payload = self._decode_object(response)
                error_value = payload.get("error")
                message = error_value if isinstance(error_value, str) else response.text
            except ApiError:
                message = response.text
            raise ApiError(
                f"{method} /api/{path} failed ({response.status_code}): {message}"
            )

        return self._decode_object(response)

    def _get(self, path: str, **params: str) -> dict[str, object]:
        return self._request("GET", path, params=params or None)

    def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        return self._request("POST", path, json_body=body)

    @staticmethod
    def _find_by_name(
        kind: str, items: list[NamedResource], name: str
    ) -> NamedResource:
        normalized_name = name.casefold()
        exact = [item for item in items if item.name.casefold() == normalized_name]
        if exact:
            return exact[0]

        partial = [item for item in items if normalized_name in item.name.casefold()]
        if len(partial) == 1:
            return partial[0]

        candidates = ", ".join(item.name for item in (partial or items))
        reason = f"{kind} '{name}' is ambiguous or not found"
        candidate_names = candidates or "none available"
        raise ApiError(f"{reason} (candidates: {candidate_names})")

    def find_player(self, name: str) -> NamedResource:
        payload = self._get("players", search=name)
        players = require_named_resources(payload, "players")
        return self._find_by_name("Player", players, name)

    def find_point_system(self, name: str) -> NamedResource:
        payload = self._get("point-systems")
        systems = require_named_resources(payload, "pointSystems")
        return self._find_by_name("Point system", systems, name)

    def find_map_lineup(self, name: str) -> NamedResource:
        payload = self._get("map-lineups")
        lineups = require_named_resources(payload, "mapLineups")
        return self._find_by_name("Map lineup", lineups, name)

    def latest_season(self) -> NamedResource:
        payload = self._get("seasons")
        seasons = require_named_resources(payload, "seasons")
        if not seasons:
            raise ApiError("No seasons found — create one in the app first.")
        return seasons[0]

    def create_scrim(self, body: dict[str, object]) -> str:
        return require_string(self._post("scrims", body), "scrimId")

    def create_lobby(self, scrim_id: str) -> CreatedLobby:
        payload = self._post("lobbies", {"scrimId": scrim_id})
        lobby = require_object(payload, "lobby")
        return CreatedLobby(
            id=require_string(lobby, "id"),
            number=require_integer(lobby, "number"),
        )

    def add_players(self, lobby_id: str, player_ids: list[str]) -> list[str]:
        """Append players to a lobby and return the complete roster."""
        payload = self._post(
            f"lobbies/{lobby_id}/players",
            {"playerIds": player_ids},
        )
        return require_string_list(payload, "players")


def main() -> None:
    """Create the configured production scrim, lobbies, and rosters."""
    api_key = os.environ.get("SCRIMS_API_KEY")
    api_url = os.environ.get("SCRIMS_API_URL")

    if not api_key:
        message = "SCRIMS_API_KEY is not set — add it to scripts/.env"
        message += " (see scripts/.env.example) or export it in your shell."
        sys.exit(message)

    if not api_url:
        message = "SCRIMS_API_URL is not set — add it to scripts/.env"
        message += " (see scripts/.env.example) or export it in your shell."
        sys.exit(message)

    print(f"Production API: {api_url}")
    client = ScrimsClient(api_url, api_key)

    season = client.latest_season()
    print(f"Using season: {season.name} ({season.id})")

    scrim_body: dict[str, object] = {
        "name": SCRIM_NAME,
        "type": SCRIM_TYPE,
        "seasonId": season.id,
        "isPrivate": IS_PRIVATE,
    }

    if POINT_SYSTEM_NAME:
        point_system = client.find_point_system(POINT_SYSTEM_NAME)
        scrim_body["pointSystemId"] = point_system.id
        print(f"Using point system: {point_system.name} ({point_system.id})")

    if MAP_LINEUP_NAME:
        map_lineup = client.find_map_lineup(MAP_LINEUP_NAME)
        scrim_body["mapLineupId"] = map_lineup.id
        print(f"Using map lineup: {map_lineup.name} ({map_lineup.id})")

    scrim_id = client.create_scrim(scrim_body)
    print(f"Created scrim: {scrim_id}")

    for roster in LOBBY_ROSTERS:
        lobby = client.create_lobby(scrim_id)
        print(f"Created lobby {lobby.number}: {lobby.id}")
        if roster:
            player_ids = [client.find_player(name).id for name in roster]
            players_in_lobby = client.add_players(lobby.id, player_ids)
            player_names = ", ".join(roster)
            print(f"  added {player_names} ({len(players_in_lobby)} in lobby)")

    delete_url = f"{api_url}/api/scrims/{scrim_id}"
    delete_command = (
        f'curl -X DELETE -H "Authorization: Bearer $SCRIMS_API_KEY" {delete_url}'
    )
    print(f"Delete it all with: {delete_command}")


if __name__ == "__main__":
    try:
        main()
    except ApiError as error:
        sys.exit(str(error))
    except requests.RequestException as error:
        sys.exit(f"Could not reach the production API: {error}")
