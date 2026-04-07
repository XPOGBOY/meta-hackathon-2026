"""
Training script for the DQN agent on the Warehouse Logistics Environment.

Usage:
    python -m warehouse_env.train

The trained model is saved as 'warehouse_model.pth' in the project root.
"""
import os
import time

from warehouse_env.client import WarehouseEnv
from warehouse_env.models import WarehouseAction
from warehouse_env.agent import DQNAgent, encode_state, TARGET_UPDATE

# ──────────────────────────────────────────
# Training Config
# ──────────────────────────────────────────
NUM_EPISODES    = 5000
MAX_STEPS       = 100
API_BASE_URL    = os.getenv("API_BASE_URL", "ws://127.0.0.1:8002")
SAVE_PATH       = os.path.join(os.path.dirname(__file__), "warehouse_model.pth")
LOG_EVERY       = 100   # print stats every N episodes


def train():
    agent = DQNAgent()

    print("=" * 60)
    print("  Warehouse DQN Training  —  PyTorch RL")
    print("=" * 60)
    print(f"  Episodes : {NUM_EPISODES}")
    print(f"  Max Steps: {MAX_STEPS}")
    print(f"  Server   : {API_BASE_URL}")
    print("=" * 60)
    start_time = time.time()

    with WarehouseEnv(base_url=API_BASE_URL).sync() as env:
        for episode in range(1, NUM_EPISODES + 1):
            result   = env.reset()
            obs      = result.observation
            state    = encode_state(obs.robot_pos, obs.items_left, obs.inventory)
            done     = False
            ep_reward = 0.0
            steps    = 0

            while not done and steps < MAX_STEPS:
                action_id = agent.select_action(state)
                result    = env.step(WarehouseAction(action_id=action_id))
                next_obs  = result.observation
                reward    = result.reward or 0.0
                done      = result.done

                next_state = encode_state(next_obs.robot_pos, next_obs.items_left, next_obs.inventory)
                agent.store(state, action_id, reward, next_state, float(done))
                agent.learn()

                state      = next_state
                ep_reward += reward
                steps     += 1

            agent.decay_epsilon()

            if episode % TARGET_UPDATE == 0:
                agent.update_target()

            if episode % LOG_EVERY == 0:
                elapsed = time.time() - start_time
                print(
                    f"  Episode {episode:>5}/{NUM_EPISODES}  |  "
                    f"Reward: {ep_reward:+.2f}  |  "
                    f"Steps: {steps:>3}  |  "
                    f"Epsilon: {agent.epsilon:.3f}  |  "
                    f"Time: {elapsed:.0f}s"
                )

    agent.save(SAVE_PATH)
    print("\n[DONE] Training complete!")
    print(f"[DONE] Model saved → {SAVE_PATH}")


if __name__ == "__main__":
    train()
