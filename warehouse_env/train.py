"""DQN training loop for the adaptive warehouse environment.

This script wires three independent components into a single training run:

* The :class:`WarehouseEnv` client, which talks to the OpenEnv server
  exposing :class:`WarehouseEnvironment`.
* The :class:`DQNAgent`, which owns the policy/target networks, the
  replay buffer, and the epsilon-greedy action selector.
* The :class:`PerformanceTracker` + :class:`CurriculumController`, which
  watch the agent's recent scores and promote / demote it across the
  curriculum levels (``simple_order`` -> ``adaptive_fulfillment``).

Action masking (see :func:`_select_masked_action`) is the key trick:
instead of letting the DQN waste exploration budget proposing illegal
moves (walking into walls, picking on empty cells, delivering with an
empty inventory), we restrict its argmax to the set of legal action ids
for the current observation. This produces dramatically faster learning
on the more crowded curriculum levels.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List

import torch

from warehouse_env.agent import DQNAgent, TARGET_UPDATE, encode_state
from warehouse_env.client import WarehouseEnv
from warehouse_env.models import WarehouseAction, WarehouseObservation
from warehouse_env.self_improve import CurriculumController, EpisodeRecord, PerformanceTracker

# Number of full episodes to run end-to-end. 2000 is enough to see
# stable curriculum progression on a single A10G GPU in roughly an hour.
NUM_EPISODES: int = 2000
API_BASE_URL: str = os.getenv("API_BASE_URL", "ws://127.0.0.1:8000")
SAVE_PATH: str = os.path.join(os.path.dirname(__file__), "warehouse_model.pth")
LOG_EVERY: int = 50
PLOTS_DIR: Path = Path(__file__).parent.parent / "docs" / "plots"


def _valid_action_ids(observation: WarehouseObservation, grid_size: tuple) -> List[int]:
    """Return the subset of action ids that are legal in the current observation.

    Legality rules:
        * A move (0-3) is legal iff its target cell is in-grid and not
          an obstacle.
        * Pick (4) is legal iff there is a still-pickable order item at
          the robot's current cell.
        * Deliver (5) is legal iff the robot is on the active order's
          staging zone *and* its inventory is non-empty.

    If no action is legal at all (extremely rare — e.g. the robot is
    walled in by dynamic obstacles), we fall back to the four movement
    ids so the policy network still has something to choose from.

    Args:
        observation: The current :class:`WarehouseObservation`.
        grid_size: ``(width, height)`` of the grid.

    Returns:
        A sorted, de-duplicated list of legal action ids.
    """
    width, height = grid_size
    robot_x, robot_y = observation.robot_pos
    blocked_cells = set(observation.obstacles)
    valid_actions: List[int] = []

    move_candidates = {
        0: (robot_x, robot_y - 1),
        1: (robot_x, robot_y + 1),
        2: (robot_x - 1, robot_y),
        3: (robot_x + 1, robot_y),
    }
    for action_id, (next_x, next_y) in move_candidates.items():
        if 0 <= next_x < width and 0 <= next_y < height and (next_x, next_y) not in blocked_cells:
            valid_actions.append(action_id)

    current_order = observation.current_order
    if current_order is not None:
        if any(
            item.position == observation.robot_pos and item.in_stock and not item.picked and not item.delivered
            for item in current_order.items
        ):
            valid_actions.append(4)

        if observation.inventory and any(
            zone.contains(observation.robot_pos) and zone.name == current_order.delivery_zone
            for zone in observation.delivery_zones
        ):
            valid_actions.append(5)

    if not valid_actions:
        return [0, 1, 2, 3]
    return sorted(set(valid_actions))


def _select_masked_action(agent: DQNAgent, state_vec, valid_action_ids: List[int]) -> int:
    """Epsilon-greedy action selection restricted to a set of legal actions.

    Implements action masking by adding ``-inf`` to the Q-value of every
    illegal action before the argmax. This is mathematically equivalent
    to taking the argmax over the legal subset, but keeps the entire
    operation on a single tensor.

    Args:
        agent: The :class:`DQNAgent` whose policy network produces Q-values.
        state_vec: Encoded state vector (numpy array or list of floats).
        valid_action_ids: Action ids the agent is allowed to choose from.

    Returns:
        The selected action id.
    """
    if not valid_action_ids:
        return agent.select_action(state_vec)

    # Exploration branch: uniform random over the legal subset only.
    # Using torch RNG keeps reproducibility consistent with the agent.
    if torch.rand(1).item() < agent.epsilon:
        return valid_action_ids[torch.randint(len(valid_action_ids), (1,)).item()]

    # Exploitation branch: mask illegal actions to -inf so they never
    # win the argmax. Doing this on-tensor avoids a Python-level loop.
    with torch.no_grad():
        tensor_state = torch.tensor(state_vec, dtype=torch.float32, device=agent.device).unsqueeze(0)
        q_values = agent.policy_net(tensor_state).squeeze(0)
        mask = torch.full_like(q_values, float("-inf"))
        mask[valid_action_ids] = 0.0
        masked_q_values = q_values + mask
        return int(masked_q_values.argmax().item())


def save_training_results(
    episode_scores: List[float],
    episode_losses: List[float],
    baseline_score: float,
) -> None:
    """Render the training curves and dump a metrics summary to ``docs/plots/``.

    Generates three artifacts:
        * ``training_reward.png`` — raw + smoothed score per episode,
          with a horizontal line at the baseline.
        * ``training_loss.png``   — raw + smoothed TD loss per episode.
        * ``metrics.json``        — final / average / improvement %.

    The matplotlib import is intentionally lazy and inside a ``try`` so
    headless CI runs without the optional dependency still get the JSON.

    Args:
        episode_scores: Per-episode final clamped scores.
        episode_losses: Per-episode mean TD loss (only collected on
            episodes where at least one optimizer step happened).
        baseline_score: Mean score over the first 50 episodes, used as
            the dashed reference line on the reward plot.
    """
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib  # type: ignore
        matplotlib.use("Agg")  # Headless backend — no display required.
        import matplotlib.pyplot as plt  # type: ignore

        # Reward curve: a moving average over a window of up to 50
        # episodes smooths out the noise from individual episode swings.
        smoothing_window = min(50, len(episode_scores))
        smoothed_scores = [
            sum(episode_scores[max(0, i - smoothing_window): i + 1])
            / len(episode_scores[max(0, i - smoothing_window): i + 1])
            for i in range(len(episode_scores))
        ]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(episode_scores, alpha=0.25, color="#4C9BE8", label="Raw score")
        ax.plot(
            smoothed_scores,
            color="#1A5FA8",
            linewidth=2,
            label=f"Smoothed (window={smoothing_window})",
        )
        ax.axhline(
            baseline_score,
            color="#E84C4C",
            linestyle="--",
            linewidth=1.5,
            label=f"Baseline ({baseline_score:.3f})",
        )
        ax.set_xlabel("Episode")
        ax.set_ylabel("Score")
        ax.set_title("DQN Training - Episode Score (Adaptive Warehouse)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        reward_path = PLOTS_DIR / "training_reward.png"
        fig.savefig(reward_path, dpi=150)
        plt.close(fig)
        print(f"Saved reward plot -> {reward_path}")

        # Loss curve: same smoothing approach, gated on whether any
        # optimizer steps actually happened (early episodes can have
        # zero learn() calls if the replay buffer is still warming up).
        if episode_losses:
            loss_window = min(50, len(episode_losses))
            smoothed_losses = [
                sum(episode_losses[max(0, i - loss_window): i + 1])
                / len(episode_losses[max(0, i - loss_window): i + 1])
                for i in range(len(episode_losses))
            ]
            fig2, ax2 = plt.subplots(figsize=(10, 5))
            ax2.plot(episode_losses, alpha=0.25, color="#E8A44C", label="Raw loss")
            ax2.plot(
                smoothed_losses,
                color="#A85A1A",
                linewidth=2,
                label=f"Smoothed (window={loss_window})",
            )
            ax2.set_xlabel("Episode")
            ax2.set_ylabel("TD Loss")
            ax2.set_title("DQN Training - TD Loss (Adaptive Warehouse)")
            ax2.legend()
            ax2.grid(alpha=0.3)
            fig2.tight_layout()
            loss_path = PLOTS_DIR / "training_loss.png"
            fig2.savefig(loss_path, dpi=150)
            plt.close(fig2)
            print(f"Saved loss plot  -> {loss_path}")

    except ImportError:
        print("matplotlib not installed - skipping plot generation. Run: pip install matplotlib")

    # Metrics JSON is always written, even without matplotlib, so CI
    # runs and headless training environments still produce a tracked
    # artifact for the README and the leaderboard.
    final_score = episode_scores[-1] if episode_scores else 0.0
    final_window = min(50, len(episode_scores))
    final_avg = sum(episode_scores[-final_window:]) / max(final_window, 1)
    improvement_pct = (
        round((final_avg - baseline_score) / max(baseline_score, 0.001) * 100, 1)
        if baseline_score > 0
        else 0.0
    )
    metrics = {
        "episodes": len(episode_scores),
        "baseline_score": round(baseline_score, 4),
        "final_score": round(final_score, 4),
        "final_avg_score": round(final_avg, 4),
        "improvement_pct": improvement_pct,
        "algorithm": "DQN with curriculum learning",
        "curriculum_levels": ["simple_order", "multi_step_order", "order_queue", "adaptive_fulfillment"],
    }
    metrics_path = PLOTS_DIR / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))
    print(f"Saved metrics    -> {metrics_path}")


def train() -> None:
    """Run the full DQN training loop end-to-end.

    Side effects:
        * Writes the trained policy network weights to :data:`SAVE_PATH`.
        * Writes training plots and metrics into :data:`PLOTS_DIR`.
        * Prints a per-:data:`LOG_EVERY` progress summary to stdout.
    """
    agent = DQNAgent(device=os.getenv("TORCH_DEVICE", "cpu"))
    tracker = PerformanceTracker(max_episodes=40)
    curriculum = CurriculumController(initial_level="simple_order")

    print("=" * 64)
    print("Adaptive Warehouse DQN Training")
    print("=" * 64)
    print(f"Episodes : {NUM_EPISODES}")
    print(f"Server   : {API_BASE_URL}")
    print("=" * 64)

    # Per-episode time series we'll feed to the plotter at the end.
    episode_scores: List[float] = []
    episode_losses: List[float] = []
    baseline_score: float = 0.0

    started_at = time.time()
    with WarehouseEnv(base_url=API_BASE_URL).sync() as env:
        for episode in range(1, NUM_EPISODES + 1):
            task_name = curriculum.current_level
            result = env.reset(task_name=task_name)
            state_payload = env.state()
            observation = result.observation
            state_vec = encode_state(observation, state_payload.grid_size)
            done = False
            episode_reward = 0.0
            episode_loss_total = 0.0
            optimizer_steps = 0

            while not done and state_payload.step_count < state_payload.max_steps:
                # Action masking is the key efficiency win here: we never
                # let the DQN even consider an illegal action, which
                # collapses an enormous chunk of the early-training
                # exploration space.
                valid_action_ids = _valid_action_ids(observation, state_payload.grid_size)
                action_id = _select_masked_action(agent, state_vec, valid_action_ids)
                result = env.step(WarehouseAction(action_id=action_id))
                next_state_payload = env.state()
                next_observation = result.observation
                next_state_vec = encode_state(next_observation, next_state_payload.grid_size)
                reward = float(result.reward or 0.0)
                done = bool(result.done)

                agent.store(state_vec, action_id, reward, next_state_vec, float(done))
                loss = agent.learn()
                if loss is not None:
                    episode_loss_total += loss
                    optimizer_steps += 1

                state_vec = next_state_vec
                state_payload = next_state_payload
                observation = next_observation
                episode_reward += reward

            agent.decay_epsilon()
            if episode % TARGET_UPDATE == 0:
                agent.update_target()

            priority_compliance = (
                state_payload.priority_compliant_actions / float(state_payload.priority_actions)
                if state_payload.priority_actions > 0
                else 1.0
            )
            efficiency_ratio = max(
                0.0,
                1.0 - (state_payload.step_count / float(max(state_payload.max_steps, 1))),
            )
            failure_reasons: List[str] = []
            if state_payload.failed_orders:
                failure_reasons.append(
                    "deadline_missed" if state_payload.task_name != "simple_order" else "incomplete"
                )
            if state_payload.dependency_violations:
                failure_reasons.append("dependency_violation")

            tracker.record_episode(
                EpisodeRecord(
                    task_name=task_name,
                    score=state_payload.score,
                    steps_taken=state_payload.step_count,
                    orders_completed=len(state_payload.completed_orders),
                    total_orders=state_payload.total_orders_expected,
                    failure_reasons=failure_reasons,
                    priority_compliance=priority_compliance,
                    efficiency_ratio=efficiency_ratio,
                )
            )
            curriculum.update(tracker)

            episode_scores.append(state_payload.score)
            if optimizer_steps > 0:
                episode_losses.append(episode_loss_total / optimizer_steps)

            # Snapshot the baseline once we have a stable rolling sample
            # — used as the reference line on the reward plot and as the
            # denominator of the improvement-percentage metric.
            if episode == 50:
                baseline_score = tracker.baseline_score()

            if episode % LOG_EVERY == 0:
                elapsed = time.time() - started_at
                print(
                    f"Episode {episode:>4}/{NUM_EPISODES} | "
                    f"task={task_name:<20} | "
                    f"score={state_payload.score:.4f} | "
                    f"reward={episode_reward:+.3f} | "
                    f"steps={state_payload.step_count:>3} | "
                    f"epsilon={agent.epsilon:.3f} | "
                    f"time={elapsed:.0f}s"
                )
                print(f"  History: {tracker.summary()}")

    agent.save(SAVE_PATH)
    print(f"Training complete. Model saved to {SAVE_PATH}")

    print("\nGenerating training plots...")
    save_training_results(episode_scores, episode_losses, baseline_score)


if __name__ == "__main__":
    train()
