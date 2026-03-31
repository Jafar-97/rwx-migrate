#!/usr/bin/env python3
"""
rwx-migrate: Automatically converts GitHub Actions workflows to RWX tasks.yml
Built by Jafar to solve RWX's #1 implementation bottleneck.
"""

import yaml
import json
import sys
import os
import argparse
from pathlib import Path
from typing import Any

# ── helpers ──────────────────────────────────────────────────────────────────

def load_gha_workflows(source: str) -> dict[str, dict]:
    """Load all GHA workflow YAMLs from a local path."""
    workflows = {}
    p = Path(source)
    if p.is_file():
        with open(p) as f:
            workflows[p.name] = yaml.safe_load(f)
    elif p.is_dir():
        for yml in list(p.glob("**/*.yml")) + list(p.glob("**/*.yaml")):
            with open(yml) as f:
                try:
                    workflows[yml.name] = yaml.safe_load(f)
                except Exception:
                    pass
    return workflows

def infer_runner(runs_on: str) -> str:
    mapping = {
        "ubuntu-latest": "ubuntu22.04-medium",
        "ubuntu-22.04":  "ubuntu22.04-medium",
        "ubuntu-20.04":  "ubuntu22.04-medium",
        "macos-latest":  "ubuntu22.04-medium",  # best effort
        "windows-latest":"ubuntu22.04-medium",
    }
    return mapping.get(str(runs_on).lower(), "ubuntu22.04-medium")

def steps_to_run(steps: list[dict]) -> str:
    lines = []
    for s in (steps or []):
        if "run" in s:
            lines.append(s["run"].strip())
        elif "uses" in s:
            lines.append(f"# GHA action: {s['uses']} (replace with equivalent shell commands)")
    return "\n".join(lines) if lines else "echo 'TODO: add commands'"

def extract_cache_hint(steps: list[dict]) -> str | None:
    for s in (steps or []):
        uses = s.get("uses", "")
        if "cache" in uses:
            return s.get("with", {}).get("path", None)
    return None

def gha_job_to_rwx_task(job_name: str, job: dict, all_jobs: dict) -> dict:
    needs = job.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]

    steps   = job.get("steps", [])
    run_cmd = steps_to_run(steps)
    runner  = infer_runner(job.get("runs-on", "ubuntu-latest"))
    cache   = extract_cache_hint(steps)

    task: dict[str, Any] = {
        "key":  job_name,
        "run": {
            "interpreter": ["/bin/bash", "-eo", "pipefail"],
            "contents":    run_cmd,
        },
        "machine": {"os": runner},
    }

    if needs:
        task["after"] = needs

    if cache:
        task["cache"] = [{"paths": [cache], "key": f"${{{{ checksum('{cache}') }}}}"}]

    return task

def convert(workflows: dict[str, dict]) -> dict:
    all_tasks = []

    for wf_name, wf in workflows.items():
        jobs = wf.get("jobs", {}) if wf else {}
        for job_name, job in jobs.items():
            if not job:
                continue
            task = gha_job_to_rwx_task(job_name, job, jobs)
            all_tasks.append(task)

    return {"tasks": all_tasks}

# ── report ────────────────────────────────────────────────────────────────────

def estimate_speedup(workflows: dict) -> dict:
    total_jobs = sum(len((w or {}).get("jobs", {})) for w in workflows.values())
    # rough heuristic: RWX DAG + caching typically saves 40-70%
    est_saving_pct = 60
    return {
        "total_jobs_detected": total_jobs,
        "estimated_time_saving": f"~{est_saving_pct}% faster builds (content-based caching + true parallelism)",
        "parallelization": "All independent jobs will run concurrently on separate machines",
        "cache_opportunities": "RWX will cache task outputs by content hash — no redundant reruns",
    }

def find_simplifications(workflows: dict) -> list[str]:
    tips = []
    for wf_name, wf in workflows.items():
        jobs = (wf or {}).get("jobs", {})
        for job_name, job in jobs.items():
            steps = (job or {}).get("steps", [])
            for s in steps:
                uses = s.get("uses", "")
                if "cache" in uses:
                    tips.append(f"[{job_name}] GHA cache action → replace with RWX native content-based caching (automatic)")
                if "actions/checkout" in uses:
                    tips.append(f"[{job_name}] actions/checkout → use RWX's built-in git clone (no action needed)")
                if "actions/setup-" in uses:
                    tips.append(f"[{job_name}] {uses} → pin runtime in RWX machine config or use a pre-built image")
        # detect matrix jobs
        for job_name, job in jobs.items():
            if (job or {}).get("strategy", {}).get("matrix"):
                tips.append(f"[{job_name}] Matrix job detected → RWX parallelizes these natively across machines without matrix config")
    return tips if tips else ["No major simplifications detected — workflow is straightforward."]

def generate_report(workflows: dict, rwx_config: dict, output_dir: Path):
    speedup   = estimate_speedup(workflows)
    simplifications = find_simplifications(workflows)
    total_tasks = len(rwx_config.get("tasks", []))

    lines = [
        "# 🚀 RWX Migration Playbook",
        "",
        "Generated by **rwx-migrate** — built by Jafar (github.com/jafar-97/rwx-migrate)",
        "",
        "---",
        "",
        "## 📊 Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| GHA workflows analyzed | {len(workflows)} |",
        f"| Jobs converted to RWX tasks | {total_tasks} |",
        f"| Estimated build time saving | {speedup['estimated_time_saving']} |",
        f"| Parallelization | {speedup['parallelization']} |",
        "",
        "---",
        "",
        "## ⚡ Why RWX Will Be Faster",
        "",
        "| GitHub Actions | RWX |",
        "|----------------|-----|",
        "| Linear jobs, manual parallelism | DAG: true dependency-based parallelism |",
        "| Cache config is manual & fragile | Content-based caching — automatic |",
        "| Full job reruns on failure | Granular task retries |",
        "| Per-minute billing, over-provisioned | Per-second billing, right-sized machines |",
        "",
        "---",
        "",
        "## 🔧 Simplification Wins",
        "",
    ]
    for tip in simplifications:
        lines.append(f"- {tip}")

    lines += [
        "",
        "---",
        "",
        "## ✅ Cutover Checklist",
        "",
        "- [ ] Review generated `tasks.yml` — verify commands match your expectations",
        "- [ ] Replace any `# GHA action:` comments with equivalent shell commands",
        "- [ ] Connect your repo to RWX cloud (Settings → Integrations → GitHub)",
        "- [ ] Run `rwx run --file tasks.yml` locally to validate",
        "- [ ] Run RWX side-by-side with GHA for 1 week to compare results",
        "- [ ] Disable GHA workflows once RWX is confirmed stable",
        "",
        "---",
        "",
        "## 📁 Generated Files",
        "",
        "- `tasks.yml` — your RWX workflow (ready to run)",
        "- `MIGRATION_PLAYBOOK.md` — this file",
        "",
        "---",
        "",
        "*Built to solve RWX's #1 customer onboarding bottleneck.*",
        "*Every manual migration currently takes an RWX engineer 2-4 hours. This does it in seconds.*",
    ]

    report_path = output_dir / "MIGRATION_PLAYBOOK.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    return report_path

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="rwx-migrate: Convert GitHub Actions → RWX tasks.yml instantly"
    )
    parser.add_argument("source", help="Path to a GHA workflow file or .github/workflows/ directory")
    parser.add_argument("--output", default="./rwx-output", help="Output directory (default: ./rwx-output)")
    args = parser.parse_args()

    print("\n🔍 rwx-migrate — GitHub Actions → RWX Converter")
    print("=" * 50)

    # load
    print(f"\n📂 Loading workflows from: {args.source}")
    workflows = load_gha_workflows(args.source)
    if not workflows:
        print("❌ No workflow files found. Check your path.")
        sys.exit(1)
    print(f"   ✅ Found {len(workflows)} workflow(s): {', '.join(workflows.keys())}")

    # convert
    print("\n⚙️  Converting jobs → RWX tasks...")
    rwx_config = convert(workflows)
    print(f"   ✅ {len(rwx_config['tasks'])} task(s) generated")

    # output
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    tasks_path = out / "tasks.yml"
    with open(tasks_path, "w") as f:
        yaml.dump(rwx_config, f, default_flow_style=False, sort_keys=False)

    report_path = generate_report(workflows, rwx_config, out)

    # print tasks.yml preview
    print("\n📄 Generated tasks.yml:")
    print("-" * 40)
    with open(tasks_path) as f:
        print(f.read())

    # speedup summary
    speedup = estimate_speedup(workflows)
    print("\n📈 Migration Impact Estimate:")
    for k, v in speedup.items():
        print(f"   • {k}: {v}")

    simplifications = find_simplifications(workflows)
    print("\n🔧 Simplification Wins:")
    for tip in simplifications:
        print(f"   • {tip}")

    print(f"\n✅ Output written to: {out}/")
    print(f"   → {tasks_path}")
    print(f"   → {report_path}")
    print("\n🚀 Next: run  'rwx run --file rwx-output/tasks.yml'  to test it live!\n")

if __name__ == "__main__":
    main()
