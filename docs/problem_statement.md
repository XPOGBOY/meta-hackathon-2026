# Adaptive Warehouse Order Fulfillment with Natural Language Instructions and Self-Improving Planning

## 1. Problem Statement

This project models a warehouse AI agent that receives multi-step fulfillment orders in natural language and must convert them into reliable, efficient action sequences. The agent must parse instructions, plan routes that respect item priorities, dependencies, fragile-handling constraints, and deadlines, execute those plans in a grid-based warehouse, and improve over time by using episode history to refine future decisions.

## 2. Environment

The environment is a grid-based warehouse built with the OpenEnv framework. It contains four storage zones, `A`, `B`, `C`, and `D`, plus two delivery staging areas at the warehouse edge.

Each episode includes:

- Natural-language order instructions
- Item lists with positions, priorities, and fragile flags
- Dependency constraints such as “pick foam insert before fragile sensor”
- Delivery targets
- Optional deadlines

Dynamic elements include:

- New orders arriving mid-episode
- Items that may be out of stock
- Obstacles that shift between episodes

The action space has six actions:

- `0`: up
- `1`: down
- `2`: left
- `3`: right
- `4`: pick
- `5`: deliver

The observation space is fully observable and includes the robot position, visible items, active order, queue size, inventory, delivery zones, deadline countdown, and a summary of recent episode performance.

## 3. Agent Capabilities

The agent supports the following capabilities:

- Natural-language instruction parsing via an LLM, with a heuristic fallback when the proxy is unavailable
- Topological dependency resolution over item prerequisites
- BFS pathfinding for shortest-path movement
- TSP-style ordering for efficient pickup sequencing
- Priority-aware execution for urgent and high-value items
- Self-improvement through episode memory, performance tracking, and LLM-generated strategy hints

## 4. Tasks

### `simple_order`

- Grid: 5x5
- Items: 2
- Orders: 1
- Max steps: 45
- Features: no dependencies, short deadline, basic delivery loop

### `multi_step_order`

- Grid: 10x10
- Items: 4
- Orders: 1
- Max steps: 100
- Features: dependencies, priorities, fragile items

### `order_queue`

- Grid: 10x10
- Orders: 3 sequential orders
- Max steps: 120
- Features: varying order complexity, repeated plan-execute-deliver cycles

### `adaptive_fulfillment`

- Grid: 15x15
- Orders: 5 total orders
- Max steps: 180
- Features: dynamic arrivals, deadlines, stock shortages, more difficult queue management

## 5. Reward Model

The reward function is fully algorithmic and does not use a human or LLM judge.

Per-step components:

- Item pickup: `0.1 * priority`
- Dependency compliance: `+0.15`
- Dependency violation: `-0.2`
- Correct delivery: `+0.3`
- Wrong delivery: `-0.3`
- Order completion: `+0.5`
- Deadline bonus: proportional to remaining slack
- Efficiency penalty: `-0.001` per step

Episode-level score:

- `completion_ratio * 0.5`
- `priority_compliance * 0.2`
- `efficiency * 0.15`
- `improvement * 0.15`

Scores are clamped into the hackathon-safe range `0.0001` to `0.9999`.

## 6. Self-Improvement Strategy

The self-improvement design is intentionally practical:

- Episode memory stores the last 25 episodes
- Performance tracking summarizes average score, completion rate, and failure trends
- Curriculum learning automatically advances when the score stays above `0.8` for three consecutive episodes
- LLM-powered strategy adaptation feeds recent episode history back into the planner as a short hint for the next run
- The PyTorch DQN training loop follows the same curriculum progression

This creates a feedback loop in which the agent does not just execute instructions; it also becomes more informed by recent performance and failure modes as episodes accumulate.
