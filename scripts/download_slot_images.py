#!/usr/bin/env python3
"""Aggregate slot/config render images from GitHub Actions artifacts.

The Slot Documentation page needs one render image per base slot AND per
generated IO-configuration variant. Those images are produced as
``<name>_image`` artifacts by the "CI" and "IO Configurations" workflows.

A naive "pick one successful run" strategy is fragile: the IO Configurations
workflow builds ~74+ jobs, so a single flaky job marks the whole run
``failure`` even though 73 fresh images exist. Selecting only
success/cancelled runs then falls back to a stale run (few configs) or one
whose artifacts have expired, leaving ``-`` placeholders on the page.

This script instead walks recent runs **newest-first, conclusion-agnostic**
and backfills each ``(slot, variant)`` image from the newest run that still
has a non-expired artifact for it. A ``failure`` run with 73/74 images is
strictly better than an old ``success`` run with 25, so newest-wins
aggregation across runs maximises coverage and freshness.

Usage:
    uv run scripts/download_slot_images.py \
        --repo owner/name --branch <branch> --out _site/images \
        [--max-runs 60]

Requires the ``gh`` CLI authenticated (GH_TOKEN in CI).
"""
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKFLOWS = ["IO Configurations", "CI"]


def list_runs(repo: str, branch: str, max_runs: int) -> list[dict]:
    """Recent CI/IO-Configurations runs, newest-first, any conclusion.

    Fetches branch runs and (for feature branches) main runs, then sorts the
    union newest-first by creation time so each config's image is taken from
    the freshest run that still has it.
    """
    runs: list[dict] = []
    seen: set[int] = set()
    branches = [branch] if branch == "main" else [branch, "main"]
    for br in branches:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/runs?branch={br}&per_page={max_runs}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        for run in payload.get("workflow_runs", []):
            if run["name"] in WORKFLOWS and run["id"] not in seen:
                seen.add(run["id"])
                runs.append(
                    {
                        "id": run["id"],
                        "name": run["name"],
                        "conclusion": run.get("conclusion"),
                        "created_at": run.get("created_at"),
                    }
                )
    # Newest-first overall (branch and main interleaved by creation time).
    runs.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return runs


def list_image_artifacts(repo: str, run_id: int) -> list[dict]:
    """Non-expired ``*_image`` artifacts for a run."""
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    out = []
    for art in payload.get("artifacts", []):
        name = art.get("name", "")
        if name.endswith("_image") and not art.get("expired", False):
            out.append({"name": name, "id": art["id"]})
    return out


def variant_of(png_name: str) -> str:
    """Render images come in black/white background variants."""
    return "black" if "black" in png_name.lower() else "white"


def download_artifact(repo: str, run_id: int, name: str, dest: Path) -> bool:
    """Download+extract one artifact into dest; return success."""
    with tempfile.TemporaryDirectory(dir=".") as tmp:
        proc = subprocess.run(
            ["gh", "run", "download", str(run_id), "-n", name, "-D", tmp,
             "-R", repo],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            # Expired/removed artifact or transient error: skip, try older run.
            sys.stderr.write(
                f"  ! download failed for {name} (run {run_id}): "
                f"{proc.stderr.strip()}\n"
            )
            return False
        copied = False
        for png in Path(tmp).glob("*.png"):
            slot = name[: -len("_image")]
            variant = variant_of(png.name)
            target = dest / f"{slot}_{variant}.png"
            if not target.exists():
                shutil.copy(png, target)
                copied = True
        return copied


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--branch", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-runs", type=int, default=60)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    runs = list_runs(args.repo, args.branch, args.max_runs)
    print(
        f"Considering {len(runs)} recent runs "
        f"({', '.join(WORKFLOWS)}) on {args.branch}+main, newest-first"
    )

    # Track which (slot,variant) we already have so newest wins.
    have: set[str] = set()
    total = 0
    for run in runs:
        artifacts = list_image_artifacts(args.repo, run["id"])
        wanted = [
            a
            for a in artifacts
            if a["name"][: -len("_image")] not in have
        ]
        if not wanted:
            continue
        print(
            f"run {run['id']} [{run['name']} / "
            f"{run['conclusion']}]: {len(wanted)} new image artifact(s)"
        )
        for art in wanted:
            slot = art["name"][: -len("_image")]
            if download_artifact(args.repo, run["id"], art["name"], args.out):
                have.add(slot)
                total += 1
                print(f"  + {slot}")

    print(f"Downloaded images for {total} distinct slot/config names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
