# rwx-migrate 🚀

Automatically converts GitHub Actions workflows to RWX `tasks.yml` — in seconds.

Built to solve RWX's #1 customer onboarding bottleneck: every GHA → RWX migration currently takes an implementation engineer 2-4 hours of manual work. This does the first 70% automatically.

## What it does

- Parses all GHA workflow YAMLs (jobs, steps, dependencies, runners)
- Infers the RWX DAG task graph with proper `after:` dependencies
- Detects cache opportunities and maps to RWX content-based caching
- Flags GHA-specific actions (checkout, setup-node, cache) with RWX equivalents
- Generates a ready-to-run `tasks.yml`
- Generates a `MIGRATION_PLAYBOOK.md` with speedup estimate + cutover checklist

## Usage
```bash
python3 migrate.py path/to/.github/workflows/
```

## Example output
```
🔍 rwx-migrate — GitHub Actions → RWX Converter
==================================================
✅ Found 1 workflow(s): ci.yml
✅ 5 task(s) generated
📈 Estimated time saving: ~60% faster builds
🔧 Simplification wins: 7 detected
✅ Output: tasks.yml + MIGRATION_PLAYBOOK.md
```

## Requirements
```bash
pip3 install pyyaml
```

---
Built by Jafar — Cincinnati, OH (45 min from RWX HQ in Columbus)
