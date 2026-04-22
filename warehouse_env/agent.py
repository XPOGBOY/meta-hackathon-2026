from __future__ import annotations

import random
from collections import deque
from typing import Deque, List, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from warehouse_env.models import OrderItem, WarehouseObservation

MAX_VISIBLE_ITEMS = 6
# state = robot_pos(2) + delivery_anchor(2) + inventory(1) + queue_size(1) + deadline(1) + items_completed(1) + items_total(1) + visible_items(30)
STATE_DIM = 2 + 2 + 1 + 1 + 1 + 1 + 1 + (MAX_VISIBLE_ITEMS * 5)
ACTION_DIM = 6

HIDDEN1 = 128
HIDDEN2 = 128

LR = 1e-3
GAMMA = 0.99
EPSILON_START = 1.0
EPSILON_END = 0.05
EPSILON_DECAY = 0.995
MEMORY_SIZE = 20_000
BATCH_SIZE = 64
TARGET_UPDATE = 10


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


class ReplayBuffer:
    def __init__(self, capacity: int = MEMORY_SIZE):
        self.buffer: Deque[Tuple[np.ndarray, int, float, np.ndarray, float]] = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done) -> None:
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int):
        return random.sample(self.buffer, batch_size)

    def __len__(self) -> int:
        return len(self.buffer)


def _sort_items(items: Sequence[OrderItem], robot_pos: Tuple[int, int]) -> List[OrderItem]:
    return sorted(
        items,
        key=lambda item: (
            item.delivered,
            item.picked,
            -item.priority,
            abs(item.position[0] - robot_pos[0]) + abs(item.position[1] - robot_pos[1]),
            item.name,
        ),
    )


def encode_state(observation: WarehouseObservation, grid_size: Tuple[int, int]) -> np.ndarray:
    width = max(grid_size[0] - 1, 1)
    height = max(grid_size[1] - 1, 1)

    features: List[float] = [
        observation.robot_pos[0] / width,
        observation.robot_pos[1] / height,
    ]

    delivery_anchor = (0, 0)
    items_total = 0
    items_completed = 0
    deadline_remaining = 0.0

    if observation.current_order is not None:
        delivery_anchor = observation.current_order.delivery_position
        items_total = len(observation.current_order.items)
        items_completed = sum(1 for item in observation.current_order.items if item.delivered)
        if observation.deadline_remaining is not None and observation.current_order.deadline_steps:
            deadline_remaining = observation.deadline_remaining / float(
                max(observation.current_order.deadline_steps, 1)
            )

    features.extend(
        [
            delivery_anchor[0] / width,
            delivery_anchor[1] / height,
            len(observation.inventory) / float(MAX_VISIBLE_ITEMS),
            observation.order_queue_size / 5.0,
            deadline_remaining,
            items_completed / float(max(items_total, 1)),
            items_total / float(MAX_VISIBLE_ITEMS),
        ]
    )

    sorted_items = _sort_items(observation.visible_items, observation.robot_pos)[:MAX_VISIBLE_ITEMS]
    for item in sorted_items:
        manhattan = abs(item.position[0] - observation.robot_pos[0]) + abs(item.position[1] - observation.robot_pos[1])
        features.extend(
            [
                item.position[0] / width,
                item.position[1] / height,
                item.priority / 5.0,
                1.0 if item.is_fragile else 0.0,
                manhattan / float(max(grid_size[0] + grid_size[1], 1)),
            ]
        )

    while len(sorted_items) < MAX_VISIBLE_ITEMS:
        features.extend([-1.0, -1.0, 0.0, 0.0, 0.0])
        sorted_items.append(
            OrderItem(name="", position=(0, 0), zone="", priority=0, in_stock=False)
        )

    return np.array(features, dtype=np.float32)


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

    def select_action(self, state: np.ndarray) -> int:
        if random.random() < self.epsilon:
            return random.randint(0, ACTION_DIM - 1)
        with torch.no_grad():
            tensor_state = torch.tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
            return int(self.policy_net(tensor_state).argmax(dim=1).item())

    def store(self, state, action, reward, next_state, done) -> None:
        self.memory.push(state, action, reward, next_state, done)

    def learn(self):
        if len(self.memory) < BATCH_SIZE:
            return None

        states, actions, rewards, next_states, dones = zip(*self.memory.sample(BATCH_SIZE))
        states_tensor = torch.tensor(np.array(states), dtype=torch.float32, device=self.device)
        actions_tensor = torch.tensor(actions, dtype=torch.long, device=self.device).unsqueeze(1)
        rewards_tensor = torch.tensor(rewards, dtype=torch.float32, device=self.device)
        next_states_tensor = torch.tensor(np.array(next_states), dtype=torch.float32, device=self.device)
        dones_tensor = torch.tensor(dones, dtype=torch.float32, device=self.device)

        q_values = self.policy_net(states_tensor).gather(1, actions_tensor).squeeze(1)
        with torch.no_grad():
            max_next_q = self.target_net(next_states_tensor).max(1)[0]
            target_q = rewards_tensor + GAMMA * max_next_q * (1 - dones_tensor)

        loss = nn.MSELoss()(q_values, target_q)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        return float(loss.item())

    def update_target(self) -> None:
        self.target_net.load_state_dict(self.policy_net.state_dict())

    def decay_epsilon(self) -> None:
        self.epsilon = max(EPSILON_END, self.epsilon * EPSILON_DECAY)

    def save(self, path: str = "warehouse_model.pth") -> None:
        torch.save(self.policy_net.state_dict(), path)

    def load(self, path: str = "warehouse_model.pth") -> None:
        self.policy_net.load_state_dict(torch.load(path, map_location=self.device))
        self.policy_net.eval()
