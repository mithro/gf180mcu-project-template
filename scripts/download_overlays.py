#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Download the newest ``exact_pad_overlays`` artifact for a branch.

The CI ``overlay`` job renders the exact-pad overlays straight from the built
GDS (scripts/plot_exact_pad_overlay.py) and uploads them as the
``exact_pad_overlays`` artifact.  The Slot Documentation page should publish
those *true-silicon* overlays rather than a committed model, so this fetches
the freshest one (branch first, then main) into a directory.

Non-fatal by design: if no artifact is found the page simply builds without
the overlay section.

Usage:
    uv run scripts/download_overlays.py \
        --repo owner/name --branch <branch> --out docs/overlays [--max-runs 30]

Requires the ``gh`` CLI authenticated (GH_TOKEN in CI).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def ci_runs(repo: str, branch: str, max_runs: int) -> list[int]:
    """CI run ids for the branch (then main), newest-first."""
    found: list[tuple[str, int]] = []
    seen: set[int] = set()
    for br in ([branch] if branch == "main" else [branch, "main"]):
        r = subprocess.run(
            ["gh", "api",
             f"repos/{repo}/actions/runs?branch={br}&per_page={max_runs}"],
            capture_output=True, text=True, check=True,
        )
        for run in json.loads(r.stdout).get("workflow_runs", []):
            if run["name"] == "CI" and run["id"] not in seen:
                seen.add(run["id"])
                found.append((run.get("created_at") or "", run["id"]))
    found.sort(reverse=True)
    return [rid for _, rid in found]


def has_artifact(repo: str, run_id: int) -> bool:
    r = subprocess.run(
        ["gh", "api", "--paginate",
         f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
         "--jq", '.artifacts[] | select((.name == "exact_pad_overlays") '
                 'and (.expired | not)) | .name'],
        capture_output=True, text=True, check=True,
    )
    return "exact_pad_overlays" in r.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--branch", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-runs", type=int, default=30)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    for run_id in ci_runs(args.repo, args.branch, args.max_runs):
        if not has_artifact(args.repo, run_id):
            continue
        proc = subprocess.run(
            ["gh", "run", "download", str(run_id), "-n", "exact_pad_overlays",
             "-D", str(args.out), "-R", args.repo],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            pngs = sorted(p.name for p in args.out.glob("*.png"))
            print(f"Downloaded {len(pngs)} overlay PNG(s) from CI run "
                  f"{run_id}: {', '.join(pngs)}")
            return 0
        sys.stderr.write(
            f"  ! download failed for run {run_id}: {proc.stderr.strip()}\n")

    print("No exact_pad_overlays artifact found in recent runs "
          "(page will build without the overlay section).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
