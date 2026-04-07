"""
DQN Agent for the Warehouse Logistics Environment.
Uses a simple feed-forward neural network to map state → Q-values for each action.
"""
import random
import numpy as np
from collections import deque
from typing import Tuple, List

import torch
import torch.nn as nn
import torch.optim as optim

# ──────────────────────────────────────────
# Hyper-parameters
# ──────────────────────────────────────────
GRID_SIZE     = 10
NUM_ITEMS     = 3
# robot(2) + items(6) + inventory(1) + manhattan distances to each item(3)
STATE_DIM     = 2 + NUM_ITEMS * 2 + 1 + NUM_ITEMS
ACTION_DIM    = 5                        # Up, Down, Left, Right, Pick

HIDDEN1       = 128
HIDDEN2       = 128

LR            = 1e-3
GAMMA         = 0.99          # discount factor
EPSILON_START = 1.0
EPSILON_END   = 0.05
EPSILON_DECAY = 0.995         # multiply epsilon each episode
MEMORY_SIZE   = 10_000
BATCH_SIZE    = 64
TARGET_UPDATE = 10            # update target network every N episodes


# ──────────────────────────────────────────
# Neural Network
# ──────────────────────────────────────────
class DQN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(STATE_DIM, HIDDEN1),
            nn.ReLU(),
            nn.Linear(HIDDEN1, HIDDEN2),
            nn.ReLU(),
            nn.Linear(HIDDEN2, ACTION_DIM),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ──────────────────────────────────────────
# Experience Replay Buffer
# ──────────────────────────────────────────
class ReplayBuffer:
    def __init__(self, capacity: int = MEMORY_SIZE):
        self.buffer: deque = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int):
        return random.sample(self.buffer, batch_size)

    def __len__(self):
        return len(self.buffer)


# ──────────────────────────────────────────
# State Encoding
# ──────────────────────────────────────────
def encode_state(robot_pos: Tuple, items_left: List[Tuple], inventory: int) -> np.ndarray:
    """
    Encodes the observation into a flat vector.
    Items are sorted by (x,y) so the network sees a consistent representation
    regardless of the order the server returns them.
    """
    # Sort items for consistent representation
    sorted_items = sorted(items_left)

    rx, ry = robot_pos[0] / GRID_SIZE, robot_pos[1] / GRID_SIZE
    state = [rx, ry]

    for i in range(NUM_ITEMS):
        if i < len(sorted_items):
            state += [sorted_items[i][0] / GRID_SIZE, sorted_items[i][1] / GRID_SIZE]
        else:
            state += [-1.0, -1.0]   # item already picked

    state.append(inventory / NUM_ITEMS)

    # Manhattan distances to each item (normalised) — helps with planning
    for i in range(NUM_ITEMS):
        if i < len(sorted_items):
            dist = (abs(robot_pos[0] - sorted_items[i][0]) +
                    abs(robot_pos[1] - sorted_items[i][1])) / (2 * GRID_SIZE)
            state.append(dist)
        else:
            state.append(0.0)

    return np.array(state, dtype=np.float32)


# ──────────────────────────────────────────
# DQN Agent
# ──────────────────────────────────────────
class DQNAgent:
    def __init__(self, device: str = "cpu"):
        self.device = torch.device(device)
        self.policy_net = DQN().to(self.device)
        self.target_net = DQN().to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=LR)
        self.memory = ReplayBuffer()
        self.epsilon = EPSILON_START
        self.steps_done = 0

    def select_action(self, state: np.ndarray) -> int:
        """Epsilon-greedy action selection."""
        if random.random() < self.epsilon:
            return random.randint(0, ACTION_DIM - 1)
        with torch.no_grad():
            t = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
            return self.policy_net(t).argmax(dim=1).item()

    def store(self, state, action, reward, next_state, done):
        self.memory.push(state, action, reward, next_state, done)

    def learn(self):
        if len(self.memory) < BATCH_SIZE:
            return None

        batch = self.memory.sample(BATCH_SIZE)
        states, actions, rewards, next_states, dones = zip(*batch)

        states      = torch.tensor(np.array(states),      dtype=torch.float32, device=self.device)
        actions     = torch.tensor(actions,                dtype=torch.long,    device=self.device).unsqueeze(1)
        rewards     = torch.tensor(rewards,                dtype=torch.float32, device=self.device)
        next_states = torch.tensor(np.array(next_states), dtype=torch.float32, device=self.device)
        dones       = torch.tensor(dones,                  dtype=torch.float32, device=self.device)

        # Current Q values
        q_values = self.policy_net(states).gather(1, actions).squeeze(1)

        # Target Q values (Bellman equation)
        with torch.no_grad():
            max_next_q = self.target_net(next_states).max(1)[0]
            target_q   = rewards + GAMMA * max_next_q * (1 - dones)

        loss = nn.MSELoss()(q_values, target_q)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item()

    def update_target(self):
        self.target_net.load_state_dict(self.policy_net.state_dict())

    def decay_epsilon(self):
        self.epsilon = max(EPSILON_END, self.epsilon * EPSILON_DECAY)

    def save(self, path: str = "warehouse_model.pth"):
        torch.save(self.policy_net.state_dict(), path)
        print(f"[SAVE] Model saved to {path}")

    def load(self, path: str = "warehouse_model.pth"):
        self.policy_net.load_state_dict(torch.load(path, map_location=self.device))
        self.policy_net.eval()
        print(f"[LOAD] Model loaded from {path}")
