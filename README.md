
title: Meta Hackathon 2026

# Adaptive Warehouse OpenEnv

This repository contains Arjun Madhava's OpenEnv-compliant warehouse environment for the Meta PyTorch OpenEnv Hackathon 2026 Grand Finale, held April 25-26 at Scaler School of Technology in Bangalore. The current system focuses on adaptive order fulfillment: natural-language instructions are parsed into structured plans, then executed with dependency-aware BFS/TSP routing, bounded algorithmic rewards, and a lightweight self-improvement loop.

The canonical project walkthrough lives in [warehouse_env/README.md](warehouse_env/README.md). The formal judge-facing deliverable is in [docs/problem_statement.md](docs/problem_statement.md).

## Submission Context

This project started as a Round 1 warehouse logistics environment and was extended for the finale into a Round 2 system centered on:

- Long-Horizon Planning & Instruction Following as the primary theme
- Self-Improving Agent Systems as the secondary theme

That progression matters to the design. Round 1 already had route planning and RL infrastructure, so Round 2 focused on turning simple grid navigation into multi-phase fulfillment with natural-language instructions, dependencies, deadlines, queue management, and episode-history-aware adaptation.

## Quick Overview

- Tasks: `simple_order`, `multi_step_order`, `order_queue`, `adaptive_fulfillment`, **`multi_robot_coordination`** *(NEW)*
- Actions: move up, down, left, right, pick, deliver
- Planning: LLM parser + heuristic fallback + BFS/TSP routing
- Learning: PyTorch DQN training with curriculum progression
- Feedback: completion, priority compliance, efficiency, and improvement-over-baseline

## Multi-Agent Coordination (NEW)

The `multi_robot_coordination` task introduces a second robot to the warehouse. Both agents operate on the **same grid and order queue simultaneously** — this is a genuine multi-agent episode, not two single-robot runs stitched together.

Key design choices:

- **Shared order queue.** Orders are assigned to the first available robot; re-assignment happens automatically when a robot finishes its order.
- **Collision avoidance.** If two robots plan to occupy the same cell in the same step, neither moves and both receive a penalty. This forces the policy to keep robots apart.
- **Coordination efficiency score.** The episode score penalises workload imbalance — a policy that keeps one robot idle while the other does all the work scores lower than one that divides the queue evenly.
- **Same observation model.** Each robot receives a standard `WarehouseObservation` (identical schema to the single-robot env), so existing agent code runs unchanged on each robot independently.

The environment lives in `warehouse_env/server/multi_robot_environment.py` and is registered in `openenv.yaml` as `multi_robot_coordination`. A notebook demo is in `notebooks/multi_robot_demo.ipynb`.

## Quick Results

| Metric | Baseline (early episodes) | Trained DQN (2000 episodes) | Change |
|---|---|---|---|
| Episode Reward | ~0.34 | ~0.28 | −16.9% *(curriculum adaptation)* |
| Orders Completed | ~1.2 / 5 | ~2.1 / 5 | **+75%** |
| Steps to Complete | ~187 | ~95 | **−49%** |
| Deadline Compliance | ~30% | ~42% | **+40%** |
| Priority Compliance | ~55% | ~71% | **+29%** |

*Results from 2000 episodes of curriculum-based DQN training. Score dips reflect curriculum progression to harder tasks. See [Training Evidence](#training-evidence) for full analysis.*

## Training Evidence

- [Training Reward Curve](docs/plots/training_reward.png)
- [Training Loss Curve](docs/plots/training_loss.png)
- [Metrics JSON](docs/plots/metrics.json)
- [Results Summary](results/TRAINING_SUMMARY.md)
- [Colab Notebook](notebooks/training_colab.ipynb)

## Submission Artifacts

### Storytelling
- [Blog Post](docs/BLOG_POST.md)
- [Pitch Script](docs/PITCH_SCRIPT.md)
- YouTube Video: *(link in SUBMISSION_URLS.txt)*

### Infrastructure
- GitHub: *(this repo)*
- HF Spaces: https://huggingface.co/spaces/ArjunMadhava/warehouse-env

## Local Run

```bash
pip install -r warehouse_env/requirements.txt
python -m uvicorn warehouse_env.server.app:app --host 127.0.0.1 --port 7860
python inference.py
```

To run the multi-robot environment locally (no server needed):

```python
from warehouse_env.client import reset_multi_robot, step_multi_robot

env, obs = reset_multi_robot("simple_order")
env, obs, reward, done = step_multi_robot(env, {"R1": 3, "R2": 0})
```

To retrain the DQN:

```bash
python -m warehouse_env.train
```
