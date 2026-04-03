#!/usr/bin/env python3
import yaml, sys, argparse
from pathlib import Path

def load_gha_workflows(source):
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
                except:
                    pass
    return workflows

def steps_to_run(steps):
    lines = []
    for s in (steps or []):
        if "run" in s:
            lines.append(s["run"].strip())
        elif "uses" in s:
            action = s.get("uses", "")
            if "checkout" in action:
                pass
            elif "setup-node" in action:
                v = s.get("with", {}).get("node-version", "18")
                lines.append(f"# RWX: use node {v} base image or call package")
            elif "cache" in action:
                pass
            elif "setup-python" in action:
                v = s.get("with", {}).get("python-version", "3.x")
                lines.append(f"# RWX: use python {v} base image or call package")
            else:
                lines.append(f"# TODO: replace '{action}' with shell commands")
    return "\n".join(lines) if lines else "echo 'no commands'"

def convert(workflows):
    tasks = []
    for wf_name, wf in workflows.items():
        jobs = (wf or {}).get("jobs", {})
        for job_name, job in jobs.items():
            if not job:
                continue
            needs = job.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            task = {"key": job_name}
            if needs:
                task["use"] = needs
            task["run"] = steps_to_run(job.get("steps", []))
            tasks.append(task)
    return {"tasks": tasks}

def find_simplifications(workflows):
    tips = []
    for wf_name, wf in workflows.items():
        for job_name, job in (wf or {}).get("jobs", {}).items():
            for s in (job or {}).get("steps", []):
                uses = s.get("uses", "")
                if "cache" in uses:
                    tips.append(f"[{job_name}] Remove GHA cache action — RWX caches automatically")
                if "actions/checkout" in uses:
                    tips.append(f"[{job_name}] Remove actions/checkout — RWX handles git automatically")
                if "actions/setup-" in uses:
                    tips.append(f"[{job_name}] Replace {uses} with RWX base image or call package")
            if (job or {}).get("strategy", {}).get("matrix"):
                tips.append(f"[{job_name}] Matrix job — RWX parallelizes natively, no matrix needed")
    return tips or ["No major simplifications detected."]

def main():
    parser = argparse.ArgumentParser(description="rwx-migrate: Convert GitHub Actions to RWX tasks.yml")
    parser.add_argument("source", help="GHA workflow file or .github/workflows/ directory")
    parser.add_argument("--output", default="./rwx-output")
    args = parser.parse_args()

    print("\n🔍 rwx-migrate — GitHub Actions → RWX Converter")
    print("=" * 50)

    workflows = load_gha_workflows(args.source)
    if not workflows:
        print("❌ No workflows found.")
        sys.exit(1)
    print(f"\n✅ Found {len(workflows)} workflow(s): {', '.join(workflows.keys())}")

    rwx = convert(workflows)
    print(f"✅ {len(rwx['tasks'])} task(s) generated")

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    tasks_path = out / "tasks.yml"

    with open(tasks_path, "w") as f:
        yaml.dump(rwx, f, default_flow_style=False, sort_keys=False)

    print("\n📄 Generated tasks.yml:")
    print("-" * 40)
    with open(tasks_path) as f:
        print(f.read())

    print("🔧 Simplification Wins:")
    for tip in find_simplifications(workflows):
        print(f"   • {tip}")

    print(f"\n✅ Output: {tasks_path}\n")

if __name__ == "__main__":
    main()
