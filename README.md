---
title: Meta Hackathon 2026
emoji: "🏢"
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Adaptive Warehouse OpenEnv

This repository contains an OpenEnv-compliant warehouse environment for the Meta PyTorch OpenEnv Hackathon 2026 Grand Finale. The current system focuses on adaptive order fulfillment: natural-language instructions are parsed into structured plans, then executed with dependency-aware BFS/TSP routing, bounded algorithmic rewards, and a lightweight self-improvement loop.

The canonical project walkthrough lives in [warehouse_env/README.md](warehouse_env/README.md). The formal judge-facing deliverable is in [docs/problem_statement.md](docs/problem_statement.md).

## Quick Overview

- Tasks: `simple_order`, `multi_step_order`, `order_queue`, `adaptive_fulfillment`
- Actions: move up, down, left, right, pick, deliver
- Planning: LLM parser + heuristic fallback + BFS/TSP routing
- Learning: PyTorch DQN training with curriculum progression
- Feedback: completion, priority compliance, efficiency, and improvement-over-baseline

## Local Run

```bash
pip install -r warehouse_env/requirements.txt
python -m uvicorn warehouse_env.server.app:app --host 127.0.0.1 --port 7860
python inference.py
```

To retrain the DQN after the state-shape changes:

```bash
python -m warehouse_env.train
```
