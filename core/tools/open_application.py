import json
import os
import platform
import shutil # Check Path
import subprocess # Runs system commands and starts applications
from difflib import SequenceMatcher # Compares text similarity between application names
from pathlib import Path
from langchain_core.tools import tool


def _normalize_name(name: str) -> str:
    """
    Makes application names easier to compare.
    """

    name = name.lower().strip()

    for extension in [".exe", ".lnk", ".url", ".appref-ms"]:
        if name.endswith(extension):
            name = name[: -len(extension)]

    return " ".join(name.split())


def _match_score(query: str, candidate: str) -> float:
    """
    Returns a similarity score between two application names.
    """

    query = _normalize_name(query)
    candidate = _normalize_name(candidate)

    if query == candidate:
        return 100

    if query in candidate or candidate in query:
        return 90

    query_words = query.split()

    if query_words and all(word in candidate for word in query_words):
        return 85

    return SequenceMatcher(None, query, candidate).ratio() * 100


def _find_in_path(application_name: str):
    """
    Checks whether Windows can find the application through PATH.
    """

    names = [
        application_name,
        f"{application_name}.exe",
    ]

    for name in names:
        path = shutil.which(name)

        if path:
            return path

    return None


def _find_start_menu_shortcut(application_name: str):
    """
    Searches Windows Start Menu shortcuts.
    """

    start_menu_location = [
        Path(os.environ.get("PROGRAMDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs",

        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs",
    ]

    best_match = None
    best_score = 0

    for location in start_menu_location:
        if not location.exists():
            continue

        # Searches all files and subfolders
        for file in location.rglob("*"):
            if file.suffix.lower() not in {
                ".lnk",
                ".url",
                ".appref-ms",
            }:
                continue

            score = _match_score(
                application_name,
                file.stem # Gives file name without extension
            )

            if score > best_score:
                best_score = score
                best_match = file

    if best_match and best_score >= 60:
            return best_match

    return None

def _find_windows_app(application_name: str):
    """
    Searches Windows registered Start applications.
    """

    try:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
                "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
            ),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        apps = json.loads(result.stdout)

        if isinstance(apps, dict):
            apps = [apps]

        best_app = None
        best_score = 0

        for app in apps:
            name = app.get("Name")
            app_id = app.get("AppID")

            if not name or not app_id:
                continue

            score = _match_score(
                application_name,
                name,
            )

            if score > best_score:
                best_score = score
                best_app = app

        if best_app and best_score >= 60:
            return best_app

        return None

    except Exception:
        return None


@tool
def open_application(application_name: str) -> str:
    """
    Opens an application installed on the user's Windows computer.
    """

    if platform.system() != "Windows":
        return "Application opening is currently supported only on Windows."

    application_name = application_name.strip()

    if not application_name:
        return "No application name was provided."

    path = _find_in_path(application_name)

    if path:
        try:
            subprocess.Popen([path])
            return f"Opened {application_name}."
        except Exception:
            pass

    shortcut = _find_start_menu_shortcut(application_name)

    if shortcut:
        try:
            os.startfile(str(shortcut))
            return f"Opened {shortcut.stem}."
        except Exception:
            pass


    windows_app = _find_windows_app(application_name)

    if windows_app:
        try:
            app_id = windows_app["AppID"]

            subprocess.Popen(
                [
                    "explorer.exe",
                    f"shell:AppsFolder\\{app_id}",
                ]
            )

            return f"Opened {windows_app['Name']}."

        except Exception:
            pass

    return (
        f"I couldn't find an installed application matching "
        f"'{application_name}'."
)