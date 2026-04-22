# Multi-Agent Implementation Guide

Quick code snippets to add multi-agent coordination layer. Copy & paste into your codebase.

---

## File 1: `warehouse_env/server/multi_robot_environment.py` (NEW)

```python
"""Multi-robot coordination environment for scalable oversight training."""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from warehouse_env.models import (
    Order,
    WarehouseAction,
    WarehouseGameState,
    WarehouseObservation,
)
from warehouse_env.reward import RewardContext, clamp_score, compute_reward
from warehouse_env.server.environment import WarehouseEnvironment

Position = Tuple[int, int]
RobotId = str


class Robot:
    """Individual robot agent."""

    def __init__(self, robot_id: RobotId, start_pos: Position):
        self.robot_id = robot_id
        self.pos = start_pos
        self.inventory: List = []
        self.steps_taken = 0

    def can_move_to(self, target: Position, obstacles: List[Position], grid_size: Tuple[int, int]) -> bool:
        """Check if robot can move to target position."""
        grid_w, grid_h = grid_size
        if not (0 <= target[0] < grid_w and 0 <= target[1] < grid_h):
            return False
        if target in obstacles:
            return False
        return True

    def distance_to(self, target: Position) -> float:
        """Manhattan distance to target."""
        return abs(self.pos[0] - target[0]) + abs(self.pos[1] - target[1])


class MultiRobotWarehouse(WarehouseEnvironment):
    """
    Multi-robot warehouse coordination environment.
    
    One episode: Multiple robots work concurrently on a shared queue of orders.
    Each robot has partial observability (sees nearby items only).
    Manager agent (external) assigns orders to robots.
    Reward: Completion rate + coordination efficiency (collision avoidance, no idle time).
    """

    def __init__(self, num_robots: int = 2):
        # Don't call super().__init__() — we redefine initialization
        self.num_robots = num_robots
        self.robots: Dict[RobotId, Robot] = {}
        self._state = WarehouseGameState()
        self._rng = random.Random(42)

        # Multi-robot specific state
        self.current_task = "simple_order"
        self.orders_queue: List[Order] = []
        self.completed_orders: List[Order] = []
        self.collision_count = 0
        self.robot_collisions: Dict[RobotId, int] = {}

        # Initialize robots
        for i in range(num_robots):
            robot_id = f"R{i+1}"
            start_pos = (i * 4, 0)  # Spread out robots
            self.robots[robot_id] = Robot(robot_id, start_pos)
            self.robot_collisions[robot_id] = 0

    def reset(self, task_name: str = "simple_order") -> Dict[RobotId, WarehouseObservation]:
        """Reset environment and return observations for each robot."""
        self.current_task = task_name
        self.collision_count = 0

        # Reset robots
        for robot_id, robot in self.robots.items():
            robot.pos = (int(robot_id[1]) * 4, 0)
            robot.inventory = []
            robot.steps_taken = 0
            self.robot_collisions[robot_id] = 0

        # Reset state (similar to parent)
        self._state = WarehouseGameState()
        self._state.task_name = task_name

        # For simplicity, initialize with one test order
        test_order = Order(
            order_id="order-1",
            instruction_text="Pick item A from zone A, then item B from zone B",
            delivery_zone="STAGE_1",
            delivery_position=(0, 4),
            deadline_steps=50,
        )
        self.orders_queue = [test_order]

        # Return observations for each robot (partial)
        obs_dict = {}
        for robot_id, robot in self.robots.items():
            obs = WarehouseObservation(
                robot_pos=robot.pos,
                inventory=robot.inventory,
                inventory_count=len(robot.inventory),
                order_queue_size=len(self.orders_queue),
                message=f"{robot_id} initialized at {robot.pos}",
                render=self._render_grid(),
            )
            obs_dict[robot_id] = obs

        return obs_dict

    def step(self, actions: Dict[RobotId, int]) -> Tuple[Dict[RobotId, WarehouseObservation], float, bool]:
        """
        Step all robots simultaneously.

        actions = {"R1": 0, "R2": 3, ...}  # action_id per robot
        Returns: (observations_dict, reward, done)
        """
        obs_dict = {}
        total_reward = 0.0
        all_actions_invalid = True

        # Move each robot
        for robot_id, action_id in actions.items():
            if robot_id not in self.robots:
                continue

            robot = self.robots[robot_id]

            # Interpret action
            move_deltas = {
                0: (0, -1),  # up
                1: (0, 1),  # down
                2: (-1, 0),  # left
                3: (1, 0),  # right
                4: (0, 0),  # pick
                5: (0, 0),  # deliver
            }

            if action_id in move_deltas:
                dx, dy = move_deltas[action_id]
                new_pos = (robot.pos[0] + dx, robot.pos[1] + dy)

                # Validate move
                if action_id < 4:  # Move action
                    grid_w, grid_h = self._state.grid_size
                    if 0 <= new_pos[0] < grid_w and 0 <= new_pos[1] < grid_h:
                        robot.pos = new_pos
                        robot.steps_taken += 1
                        all_actions_invalid = False

                elif action_id == 4:  # Pick
                    # Simplified: just receive reward for attempting
                    total_reward += 0.1
                    all_actions_invalid = False

                elif action_id == 5:  # Deliver
                    if robot.inventory:
                        total_reward += 0.3
                        robot.inventory.clear()
                    all_actions_invalid = False

            robot.steps_taken += 1

        # Check collisions
        positions = [robot.pos for robot in self.robots.values()]
        if len(positions) != len(set(positions)):
            self.collision_count += 1
            total_reward -= 0.1

        # Check if episode done
        done = (
            all(robot.steps_taken >= 100 for robot in self.robots.values())
            or len(self.completed_orders) == len(self.orders_queue)
        )

        # Generate observations for each robot
        for robot_id, robot in self.robots.items():
            obs = WarehouseObservation(
                robot_pos=robot.pos,
                inventory=robot.inventory,
                inventory_count=len(robot.inventory),
                order_queue_size=len(self.orders_queue),
                message=f"{robot_id}: pos={robot.pos}, steps={robot.steps_taken}",
                render=self._render_grid(),
            )
            obs_dict[robot_id] = obs

        return obs_dict, total_reward, done

    def _render_grid(self) -> str:
        """Simple ASCII representation."""
        grid_w, grid_h = self._state.grid_size
        grid = [["." for _ in range(grid_w)] for _ in range(grid_h)]

        for robot_id, robot in self.robots.items():
            x, y = robot.pos
            grid[y][x] = robot_id[1]  # R1 -> "1", R2 -> "2"

        return "\n".join("".join(row) for row in grid)

    @property
    def state(self) -> WarehouseGameState:
        """Get current game state."""
        self._state.score = clamp_score(
            min(0.9999, len(self.completed_orders) / max(len(self.orders_queue), 1) - self.collision_count * 0.05)
        )
        return self._state
```

---

## Implementation Checklist

- [ ] Copy code above to `warehouse_env/server/multi_robot_environment.py`
- [ ] Add multi-robot task to `warehouse_env/openenv.yaml` (see YAML snippet)
- [ ] Run: `python -c "from warehouse_env.server.multi_robot_environment import MultiRobotWarehouse; print('✓ Multi-robot env loads')"` 
- [ ] Test import works
- [ ] Update README: mention multi-agent coordination task
- [ ] Git commit

---

## Next Steps

See `docs/WINNING_STRATEGY.md` Part 1 for full integration guide.
See `docs/72_HOUR_SPRINT.md` Phase 2 for detailed implementation steps.
