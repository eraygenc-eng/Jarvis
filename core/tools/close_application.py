import subprocess
import csv

from difflib import SequenceMatcher
from langchain_core.tools import tool


def _normalize_name(name: str) -> str:
    """
    Makes process names easier to compare.
    """

    name = name.lower().strip()

    if name.endswith(".exe"):
        name = name[:-4]

    return " ".join(name.split())


def _match_score(query: str, candidate: str) -> float:
    """
    Returns a similarity score between application and process names.
    """

    query = _normalize_name(query)
    candidate = _normalize_name(candidate)

    if query == candidate:
        return 100

    if query in candidate or candidate in query:
        return 90

    return SequenceMatcher(None, query, candidate).ratio() * 100


def _get_running_processes() -> list[str]:
    """
    Returns a list of running process names on Windows.
    """

    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            return []

        processes = []

        for row in csv.reader(result.stdout.splitlines()):
            if row:
                processes.append(row[0])

        return processes

    except Exception:
        return []


def _find_process(application_name: str) -> str | None:
    """
    Finds the best matching running process.
    """

    processes = _get_running_processes()

    best_process = None
    best_score = 0

    for process in processes:
        score = _match_score(
            application_name,
            process
        )

        if score > best_score:
            best_score = score
            best_process = process

    if best_process and best_score >= 60:
        return best_process

    return None


@tool
def close_application(application_name: str) -> str:
    """
    Closes a running application on the user's Windows computer.
    """


    application_name = application_name.strip()

    if not application_name:
        return "No application name was provided."

    process = _find_process(application_name)

    if not process:
        return f"I couldn't find a running application matching '{application_name}'."

    try:
        result = subprocess.run(
            ["taskkill", "/IM", process, "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode == 0:
            return f"Closed {application_name}."

        return f"Failed to close {application_name}."

    except Exception as error:
        return f"Failed to close {application_name}: {error}"