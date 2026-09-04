import os
import re

from difflib import SequenceMatcher
from pathlib import Path
from langchain_core.tools import tool
from core.tools.open_application import open_application


def _get_steam_library_paths() -> list[Path]:
    """
    Returns possible Steam library folders.
    """

    common_paths = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]

    libraries = []

    for path in common_paths:
        if path.exists():
            libraries.append(path)

            library_file = path / "steamapps" / "libraryfolders.vdf"

            if library_file.exists():
                content = library_file.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                matches = re.findall(
                    r'"path"\s+"([^"]+)"',
                    content
                )

                for match in matches:
                    library_path = Path(
                        match.replace("\\\\", "\\")
                    )

                    if library_path.exists():
                        libraries.append(library_path)

    return libraries


def _get_installed_games() -> list[dict]:
    """
    Returns installed Steam games with their names and App IDs.
    """

    games = []

    for library in _get_steam_library_paths():
        steamapps = library / "steamapps"

        if not steamapps.exists():
            continue

        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                content = manifest.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                app_id_match = re.search(
                    r'"appid"\s+"(\d+)"',
                    content
                )

                name_match = re.search(
                    r'"name"\s+"([^"]+)"',
                    content
                )

                if not app_id_match or not name_match:
                    continue

                games.append(
                    {
                        "name": name_match.group(1),
                        "app_id": app_id_match.group(1),
                    }
                )

            except Exception:
                continue

    return games


def _normalize_name(name: str) -> str:
    """
    Makes game names easier to compare.
    """

    name = name.lower().strip()

    name = re.sub(
        r"[^a-z0-9ğüşöçı\s]",
        " ",
        name
    )

    return " ".join(name.split())


def _find_game(game_name: str):
    """
    Finds the best matching installed Steam game.
    """

    games = _get_installed_games()
    query = _normalize_name(game_name)

    best_game = None
    best_score = 0

    for game in games:
        candidate = _normalize_name(game["name"])

        if query == candidate:
            return game

        if query in candidate or candidate in query:
            score = 90
        else:
            score = SequenceMatcher(
                None,
                query,
                candidate
            ).ratio() * 100

        if score > best_score:
            best_score = score
            best_game = game

    if best_game and best_score >= 60:
        return best_game

    return None


@tool
def launch_game(game_name: str) -> str:
    """
    Launches an installed Steam game on the user's computer.
    """

    game_name = game_name.strip()

    if not game_name:
        return "No game name was provided."

    game = _find_game(game_name)

    if not game:
        return f"I couldn't find an installed Steam game matching '{game_name}'."

    try:
        app_id = game["app_id"]
        game_title = game["name"]

        os.startfile(
            f"steam://rungameid/{app_id}"
        )

        return f"Launching {game_title}."

    except Exception as error:
        return f"Failed to launch {game_name}: {error}"