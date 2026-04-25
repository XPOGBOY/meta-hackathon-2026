# Adaptive Warehouse — Complete Project Context Prompt

*Copy everything below this line and use it in any AI assistant (ChatGPT, Claude, etc.) to give it 100% context on this project.*

---

## PROMPT START

## Background
I am participating in the **Meta PyTorch OpenEnv Hackathon 2026 Grand Finale** (April 25-26, Scaler School of Technology, Bangalore). My name is Arjun Madhava. 
The core framework is **OpenEnv**, a framework for building reinforcement learning environments that AI agents can be trained against. The environment must be deployed on Hugging Face Spaces.

## The Themes & Problem Statement
I chose the primary theme: **Long-Horizon Planning & Instruction Following**, and the secondary theme: **Self-Improving Agent Systems**.

My problem statement: *"An AI agent operates in a grid-based warehouse and receives complex, multi-step orders described in natural language. The agent must parse NL instructions into structured sub-tasks, plan routes respecting priorities/dependencies/deadlines, execute efficiently, and improve over time using episode history."*

## The Architecture
The project is a hybrid system:
1. **The LLM Parser (`InstructionParser`)**: Parses natural-language orders into a structured JSON `ParsedPlan`. It also ranks the order queue by urgency.
2. **The Algorithmic Router**: Uses Topological Sort for item dependencies, a TSP approximation for optimal pickup ordering, and BFS for grid navigation.
3. **The Self-Improvement Loop (`StrategyAdapter` & `PerformanceTracker`)**: Tracks metrics like completion rate and failure reasons (e.g., missed deadlines). It feeds this history back to the LLM as a "strategy hint" across episodes.
4. **The Environment (`WarehouseEnvironment`)**: Strict Client/Server separation. It manages the grid, 4 zones (A, B, C, D), dynamic order arrivals mid-episode, out-of-stock items, fragile item handling, and algorithmic rewards.

## The Reward Model
The reward function is purely algorithmic and clamped strictly between `0.0001` and `0.9999` (a hard rule for the OpenEnv grader).
- **Positive**: Completing orders (+0.5), picking priority items (+0.1 * priority), correct zone delivery (+0.3), meeting deadlines.
- **Penalties**: Efficiency cost (-0.001 per step), fragile risk (-0.05), obstacle collisions, missing dependencies.
- **Episode Score**: A composite of completion ratio, priority compliance, efficiency ratio, and improvement over baseline.

## Tasks (Difficulty Tiers in `openenv.yaml`)
1. `simple_order`: 5x5 grid, 1 short order, 2 items, no deps.
2. `multi_step_order`: 10x10 grid, 1 complex order, 4 items with priorities and deps.
3. `order_queue`: 10x10 grid, 3 sequential orders.
4. `adaptive_fulfillment`: 15x15 grid, 5 dynamic orders arriving mid-episode, deadlines, stock shortages.
5. `multi_robot_coordination`: A dual-agent scenario sharing a grid and order queue.

## Key Files & Directories
- `warehouse_env/server/environment.py`: The core OpenEnv simulation logic (800+ lines).
- `warehouse_env/instruction_parser.py`: The LLM LiteLLM proxy and heuristic fallback.
- `warehouse_env/reward.py`: The composite reward logic.
- `warehouse_env/self_improve.py`: Episode memory, performance tracking, curriculum control.
- `warehouse_env/agent.py` & `warehouse_env/train.py`: PyTorch DQN RL agent and training loop.
- `inference.py`: The root entrypoint for inference (evaluating the agent).
- `notebooks/training_colab.ipynb`: DQN training notebook.
- `notebooks/llm_trl_finetuning_colab.ipynb`: Fulfills the minimum hackathon requirement by showing how to generate optimal trajectories from the environment and fine-tune an LLM (Llama-3) using Hugging Face `trl.SFTTrainer` and LoRA.
- `tests/`: Contains 12 passing unit & integration tests.
- `docs/`: Contains the `problem_statement.md`, `PITCH_SCRIPT.md`, and plot images.

## Recent Fixes Applied
- Fixed `openenv.yaml` entrypoint to `warehouse_env.server.app:app`.
- Added the `llm_trl_finetuning_colab.ipynb` to satisfy the Unsloth/TRL rule.
- Deleted legacy `server/` directory and dead redirect files to prevent autograder crashes.
- Added `test_integration.py` to ensure end-to-end loop runs without exceptions.
- Updated `README.md` and `SUBMISSION_URLS.txt` with the live Hugging Face URL: `https://huggingface.co/spaces/ArjunMadhava/warehouse-env`.

## Current Goal
I am currently preparing my final pitch, recording the demo video, and ensuring my talking points align perfectly with what judges look for (e.g., explaining the hybrid LLM + Algorithmic approach, and proving the agent actually learns).

## PROMPT END
