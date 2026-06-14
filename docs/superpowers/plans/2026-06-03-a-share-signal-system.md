# A Share Signal System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable A-share stock selection signal tool that filters, scores, ranks, and pushes strategy signals.

**Architecture:** The system is a small Python package with focused modules for domain models, strategy scoring, CSV ingestion, notification, and CLI execution. The first version runs from local CSV/demo data and keeps provider integrations behind stable interfaces.

**Tech Stack:** Python 3.11+ standard library, `unittest`, dataclasses, argparse, CSV, JSON, urllib webhook notification.

---

### File Structure

- `src/trade_signal_tool/models.py`: immutable-ish dataclasses for candidates, signals, and rejected records.
- `src/trade_signal_tool/strategy.py`: strategy configuration, hard filters, scoring, ranking, signal classification.
- `src/trade_signal_tool/data.py`: CSV parsing and serialization helpers.
- `src/trade_signal_tool/notifier.py`: console and webhook notification adapters.
- `src/trade_signal_tool/demo.py`: built-in example candidates for immediate local runs.
- `src/trade_signal_tool/cli.py`: command line entrypoint for scans.
- `tests/test_strategy.py`: strategy red-green coverage for filters and scoring.
- `tests/test_data_and_cli.py`: CSV loader and CLI output behavior.
- `data/sample_candidates.csv`: sample input file.
- `README.md`: usage, data schema, strategy rules.

### Tasks

- [ ] Write failing tests for volume ratio filtering, turnover filtering, strong signal scoring, ranking, and CSV parsing.
- [ ] Implement domain models and strategy engine until tests pass.
- [ ] Implement CSV loader and sample dataset until data tests pass.
- [ ] Implement notification and CLI scan flow.
- [ ] Run full unit tests and a CLI demo scan.
