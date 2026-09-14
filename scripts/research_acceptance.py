"""Run one real research request and save reviewable evidence and metrics.

Usage: .venv/Scripts/python.exe -X utf8 -u -m scripts.research_acceptance
Uses the configured Jarvis model. Makes real model/browser requests; no purchase.
"""

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from core.agent import JarvisAgent
from core.llm.factory import create_llm
from core.tools.browser import BrowserManager
from core.research.report import render_report_table
from config.settings import LLM_PROVIDER, OPENAI_MODEL, GEMINI_MODEL


DEFAULT_PROMPT = "Bana 1 adet Logitech Superlight 2 mouse için en ucuz güncel fiyatı araştır. Varsayılan yedi kaynağın tamamını incele; DEX, SE ve 2C modellerini dahil etme. Satın alma yapma. Doğrulanmış teklifleri satıcıları ve bağlantılarıyla raporla."


class AcceptanceStopped(Exception):
    """A local STOP file requested a controlled end with partial artifacts."""


async def wait_for_stop(root):
    while not (root / "STOP").exists():
        await asyncio.sleep(1)


async def run(args):
    root = Path("artifacts") / ("acceptance-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    root.mkdir(parents=True, exist_ok=False)
    source_manifest = {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ("core", "config", "scripts")
        for path in sorted(Path(folder).rglob("*.py"))
    }
    (root / "source-manifest.json").write_text(json.dumps(source_manifest, indent=2), encoding="utf-8")
    print("ACCEPTANCE START:", root.resolve(), flush=True)
    browser = BrowserManager(headless=args.headless)
    agent = None
    report = ""
    error = None
    started = time.perf_counter()
    try:
        async with asyncio.timeout(args.timeout):
            await browser.start()
            agent = JarvisAgent(create_llm(), browser.get_tools(), observation_store=browser.observations)
            research = asyncio.create_task(agent.run(args.prompt, interactive=False))
            stop = asyncio.create_task(wait_for_stop(root))
            try:
                completed, _ = await asyncio.wait((research, stop), return_when=asyncio.FIRST_COMPLETED)
                if research in completed:
                    report = research.result()
                else:
                    raise AcceptanceStopped()
            finally:
                for task in (research, stop):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(research, stop, return_exceptions=True)
    except Exception as exc:
        error = type(exc).__name__
        print("Acceptance interrupted:", error, flush=True)
    finally:
        elapsed = time.perf_counter() - started
        state = agent.current_comparison_state if agent else None
        if agent:
            agent._refresh_final_page_status()
        if not report and state:
            report = render_report_table(state, args.prompt)
        callback = agent.timing_callback if agent else None
        summary = {
            "prompt": args.prompt, "provider": LLM_PROVIDER,
            "model": OPENAI_MODEL if LLM_PROVIDER == "openai" else GEMINI_MODEL,
            "mcp_version": "0.0.80", "elapsed_seconds": round(elapsed, 2),
            "headless": args.headless, "source_manifest": source_manifest,
            "error": error, "sources": state.planned_sources if state else [],
            "coverage_complete": bool(state and state.coverage_complete()),
            "ready": bool(state and state.is_ready_to_return()),
            "offers": len(state.results) if state else 0,
            "verified_offers": len(state.get_verified_results()) if state else 0,
            "final_page_verified": bool(state and state.final_page_verified),
            "llm_calls": callback.llm_success_count if callback else 0,
            "input_tokens": callback.input_tokens if callback else 0,
            "output_tokens": callback.output_tokens if callback else 0,
            "cache_read_tokens": callback.cache_read_tokens if callback else 0,
            "tool_stats": callback.tool_stats if callback else {},
        }
        summary["passed"] = bool(summary["ready"] and summary["verified_offers"] > 0
                                 and summary["final_page_verified"] and error is None)
        summary["commit"] = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        snapshot = subprocess.run(["git", "diff", "--", "core", "config"], capture_output=True, check=True).stdout
        summary["tracked_diff_sha256"] = hashlib.sha256(snapshot).hexdigest()
        (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "report.md").write_text(report, encoding="utf-8")
        if state:
            (root / "state.json").write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        observations = [asdict(o) for o in browser.observations._observations.values()]
        (root / "observations.json").write_text(json.dumps(observations, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        try:
            await browser.stop()
        except Exception as exc:
            print("Browser cleanup:", type(exc).__name__)
        print("ACCEPTANCE ARTIFACT:", root.resolve(), flush=True)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--headless", action="store_true", help="Default uses the same visible browser as main.py.")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
