# The Warehouse Problem Nobody Talks About

*A behind-the-scenes look at building an adaptive multi-robot order fulfillment environment for the Meta PyTorch OpenEnv Hackathon 2026.*

---

## The Problem That Actually Matters

Walk into any modern fulfilment center and you'll see the same thing: robots that are fast but brittle. They can follow a route perfectly, but the moment the instruction changes — a last-minute priority shift, a fragile item that needs special handling, a new order arriving mid-run — the system grinds to a halt and waits for a human.

This is not a hardware problem. It is a planning problem. And it is exactly the kind of problem that language models and reinforcement learning were built to solve — together.

That is what this project is about.

---

## What I Built

The Adaptive Warehouse OpenEnv is a grid-based reinforcement learning environment in which an AI agent receives **natural-language fulfillment orders** and must convert them into reliable, efficient action sequences — under time pressure, with dependencies, with fragile items, and with the knowledge that more orders will keep arriving.

The environment is fully compliant with the **OpenEnv framework**, deployable to Hugging Face Spaces via Docker, and built on PyTorch.

Here is what a realistic order looks like inside the system:

> *"Pick the foam insert first, then the fragile sensor — it needs the foam for protection. Also grab the electronics tote and the control board. Everything goes to Staging Zone 2. The sensor is priority."*

A human warehouse worker reads that and knows exactly what to do. Teaching a machine to do the same is the actual problem.

---

## How It Works: Three Layers

### Layer 1 — Instruction Parsing

The agent does not receive a structured JSON task. It receives the natural-language instruction above and must parse it into a plan. 

An LLM (via LiteLLM or an OpenAI-compatible proxy) reads the instruction and outputs a structured plan: item names, pickup order, dependency constraints, delivery target. When the proxy is unavailable, a heuristic keyword-based fallback kicks in — the agent keeps working even without an API connection.

The key design choice here was to **never let the LLM touch the reward**. The LLM plans; the algorithmic reward function judges. This keeps evaluation stable, reproducible, and fair.

### Layer 2 — Route Planning

Once the instruction is parsed, the agent plans a route using:
- **BFS** for shortest-path movement between any two grid cells (obstacle-aware)
- **TSP-style greedy ordering** to sequence pickups efficiently
- **Topological dependency resolution** to ensure prerequisite items are always picked before the items that depend on them

This hybrid approach — learned policy for macro decisions, search-based routing for micro-navigation — turned out to be more robust than either alone. A pure DQN struggles with sparse rewards in long-horizon tasks. A pure planner cannot adapt to dynamic conditions. Together, they handle both.

### Layer 3 — Self-Improvement

The most interesting part of the system is the feedback loop. After every episode:

1. **Episode memory** stores the outcome: score, steps taken, orders completed, and failure reasons (deadline missed, dependency violated, delivery error).
2. **Performance tracking** computes average score, completion rate, and the most common failure pattern.
3. **Curriculum learning** automatically advances the agent to harder tasks when it scores above 0.8 for three consecutive episodes, and drops it back if it scores below 0.35.
4. **Strategy adaptation** feeds the recent episode history back into the LLM, which returns a one-sentence planning hint for the next run.

The result is a feedback loop in which the agent does not just execute instructions — it becomes *more informed* by recent performance and failure modes as episodes accumulate.

---

## Four Task Tiers

The environment exposes four escalating tasks, each registered in `openenv.yaml`:

| Task | Grid | Challenge |
|---|---|---|
| `simple_order` | 5×5 | One order, two items, a short deadline. Intended as a warm-up. |
| `multi_step_order` | 10×10 | Four items with a dependency chain. Fragile items that must wait for their prerequisites. |
| `order_queue` | 10×10 | Three sequential orders. The agent must rank and sequence them efficiently. |
| `adaptive_fulfillment` | 15×15 | Five orders with dynamic arrivals, deadlines, and stock shortages. The hardest tier. |

And — added for the finale — a fifth task:

| `multi_robot_coordination` | 10×10 | Two robots, shared queue, collision avoidance, workload balancing. |

---

## Multi-Robot Coordination: The Innovation Bonus

The `multi_robot_coordination` task is a genuine multi-agent episode. Both robots act **simultaneously** on the same grid:

- **Shared order queue**: orders are assigned to the first idle robot; re-assignment is automatic.
- **Collision avoidance**: if two robots target the same cell, neither moves — a built-in penalty forces the policy to keep them apart.
- **Coordination efficiency score**: the episode score penalises workload imbalance. A policy that keeps one robot idle while the other does everything scores lower than one that divides the queue evenly.

This is not two single-robot runs stitched together. It is a proper cooperative MARL environment built on top of the single-robot foundation.

---

## Training Results

The DQN agent trains for 2000 episodes under curriculum progression. Here is what the learning curve shows:

- **Episodes 1–200**: The agent is on `simple_order`. Scores are low and noisy — epsilon is still high, the policy is mostly random.
- **Episodes 200–600**: Curriculum advances to `multi_step_order`. Scores drop briefly (harder task), then climb as the agent learns dependency ordering.
- **Episodes 600–1200**: `order_queue` tier. The agent learns to rank competing orders and avoid deadline failures.
- **Episodes 1200–2000**: `adaptive_fulfillment`. Scores plateau around 0.6–0.7 — the hardest tier with dynamic arrivals is genuinely difficult.

| Metric | Baseline (random policy) | Trained DQN | Improvement |
|---|---|---|---|
| Episode Score | ~0.15 | ~0.64 | **+327%** |
| Orders Completed | 1.2 / 5 | 3.8 / 5 | **+217%** |
| Steps to Complete | ~187 | ~74 | **−60%** |

The training curves are saved to `docs/plots/` and the full metrics are in `docs/plots/metrics.json`.

---

## Why This Matters Beyond the Hackathon

Warehouse coordination is a $50B problem. But the reason I chose it is not the dollar figure — it is that the environment captures three things that real AI deployments have to get right:

1. **Natural language as the input interface.** Operators should not need to write JSON to give instructions to a robot. The parsing layer is what makes the system usable.
2. **Long-horizon planning under constraints.** Real fulfillment orders have dependencies, deadlines, and priorities that interact in non-obvious ways. A planner that ignores any of these fails.
3. **Self-improvement in deployment.** A system that learns from its own failures in production — not just in training — is a system that gets better without requiring a human to retrain it.

These three properties are not unique to warehouses. They show up in any agentic system that operates in a messy, instruction-driven, time-sensitive real world. Building and benchmarking them in a controlled environment is how we make progress.

---

## What's Next

- Multi-robot training with a shared policy vs. independent policies — does cooperation emerge?
- Dynamic obstacle avoidance using learned path planning instead of BFS
- Real-world warehouse API integration via the OpenEnv HTTP interface
- Scaling to 10+ robots and measuring coordination breakdown

The environment and all code is open-source. See the repository for instructions to run locally or on Hugging Face Spaces.

---

*Built by Arjun Madhava for the Meta PyTorch OpenEnv Hackathon 2026 Grand Finale.*  
*April 2026 | Scaler School of Technology, Bangalore*
