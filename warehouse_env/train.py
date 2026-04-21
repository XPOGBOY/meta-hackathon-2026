from __future__ import annotations

import os
import time

from warehouse_env.agent import DQNAgent, TARGET_UPDATE, encode_state
from warehouse_env.client import WarehouseEnv
from warehouse_env.models import WarehouseAction
from warehouse_env.self_improve import CurriculumController, EpisodeRecord, PerformanceTracker

NUM_EPISODES = 2000
API_BASE_URL = os.getenv("API_BASE_URL", "ws://127.0.0.1:8000")
SAVE_PATH = os.path.join(os.path.dirname(__file__), "warehouse_model.pth")
LOG_EVERY = 50


def train() -> None:
    agent = DQNAgent(device=os.getenv("TORCH_DEVICE", "cpu"))
    tracker = PerformanceTracker(max_episodes=40)
    curriculum = CurriculumController(initial_level="simple_order")

    print("=" * 64)
    print("Adaptive Warehouse DQN Training")
    print("=" * 64)
    print(f"Episodes : {NUM_EPISODES}")
    print(f"Server   : {API_BASE_URL}")
    print("=" * 64)

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

            while not done and state_payload.step_count < state_payload.max_steps:
                action_id = agent.select_action(state_vec)
                result = env.step(WarehouseAction(action_id=action_id))
                next_state_payload = env.state()
                next_observation = result.observation
                next_state_vec = encode_state(next_observation, next_state_payload.grid_size)
                reward = float(result.reward or 0.0)
                done = bool(result.done)

                agent.store(state_vec, action_id, reward, next_state_vec, float(done))
                agent.learn()

                state_vec = next_state_vec
                state_payload = next_state_payload
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
            failure_reasons = []
            if state_payload.failed_orders:
                failure_reasons.append("deadline_missed" if state_payload.task_name != "simple_order" else "incomplete")
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


if __name__ == "__main__":
    train()
