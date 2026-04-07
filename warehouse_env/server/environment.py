import random
import uuid
from typing import List, Tuple, Optional
from openenv.core.env_server import Environment
from warehouse_env.models import WarehouseAction, WarehouseObservation, WarehouseGameState

class WarehouseEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self):
        self._state = WarehouseGameState()
        self._grid_size = (10, 10)
        self._max_steps = 100
        self._obstacles = [(2, 2), (2, 3), (2, 4), (5, 5), (5, 6), (7, 2), (8, 2)]
        
    def reset(self, seed: Optional[int] = None, episode_id: Optional[str] = None, task_name: Optional[str] = None, **kwargs) -> WarehouseObservation:
        if seed is not None:
            random.seed(seed)
            
        # Defaults (Medium)
        target_items = 5
        grid_size = (10, 10)
        max_steps = 100
        obstacles = [(2, 2), (2, 3), (2, 4), (5, 5), (5, 6), (7, 2), (8, 2)]

        if task_name == "easy_picking":
            target_items = 2
            grid_size = (5, 5)
            max_steps = 50
            obstacles = [(2,2)]
        elif task_name == "hard_picking":
            target_items = 10
            grid_size = (15, 15)
            max_steps = 200
            obstacles = [(2, 2), (2, 3), (2, 4), (3, 10), (3, 11), (5, 5), (5, 6), (7, 2), (8, 2), (10,10), (10,11), (11,10)]

        self._grid_size = grid_size
        self._max_steps = max_steps
        self._obstacles = obstacles
        self._target_items_count = target_items

        self._state = WarehouseGameState(
            episode_id=episode_id or str(uuid.uuid4()),
            step_count=0,
            grid_size=self._grid_size,
            robot_pos=(0, 0),
            items=[],
            obstacles=self._obstacles,
            inventory=0,
            max_steps=self._max_steps
        )
        
        # Populate valid item spawns
        while len(self._state.items) < self._target_items_count:
            it = (random.randint(0, self._grid_size[0]-1), random.randint(0, self._grid_size[1]-1))
            if it not in self._obstacles and it not in self._state.items and it != (0,0):
                self._state.items.append(it)
                
        return self._make_observation(message=f"Starting task: {task_name}! Pick up {self._target_items_count} items!")

    def step(self, action: WarehouseAction, timeout_s: Optional[float] = None, **kwargs) -> WarehouseObservation:
        self._state.step_count += 1
        reward = 0.0
        done = False
        message = ""
        
        old_pos = self._state.robot_pos
        new_pos = list(old_pos)
        
        if action.action_id == 0:  # Up
            new_pos[1] = max(0, new_pos[1] - 1)
        elif action.action_id == 1:  # Down
            new_pos[1] = min(self._grid_size[1] - 1, new_pos[1] + 1)
        elif action.action_id == 2:  # Left
            new_pos[0] = max(0, new_pos[0] - 1)
        elif action.action_id == 3:  # Right
            new_pos[0] = min(self._grid_size[0] - 1, new_pos[0] + 1)
        elif action.action_id == 4:  # Pick
            if old_pos in self._state.items:
                self._state.items.remove(old_pos)
                self._state.inventory += 1
                reward = self._state.inventory / float(self._target_items_count)
                message = f"Picked item at {old_pos}!"
            else:
                reward = 0.0
                message = "No item here to pick."
                
        new_pos_tuple = tuple(new_pos)
        if new_pos_tuple in self._obstacles:
            reward = 0.0
            message = "Hit an obstacle!"
        else:
            self._state.robot_pos = new_pos_tuple
            
        # Completion Logic Check
        if len(self._state.items) == 0:
            done = True
            reward = 1.0
            message = "Success! All items picked."
        elif self._state.step_count >= self._max_steps:
            done = True
            reward = self._state.inventory / float(self._target_items_count)
            message = "Failed: Max steps reached."
            
        return self._make_observation(done=done, reward=reward, message=message)

    @property
    def state(self) -> WarehouseGameState:
        return self._state
        
    def render(self) -> str:
        grid = [["." for _ in range(self._grid_size[0])] for _ in range(self._grid_size[1])]
        for ox, oy in self._state.obstacles:
            grid[oy][ox] = "#"
        for ix, iy in self._state.items:
            grid[iy][ix] = "$"
        rx, ry = self._state.robot_pos
        grid[ry][rx] = "R"
        
        lines = ["+ " + "- " * self._grid_size[0] + "+"]
        for row in grid:
            lines.append("| " + " ".join(row) + " |")
        lines.append("+ " + "- " * self._grid_size[0] + "+")
        return "\n".join(lines)

    def _make_observation(self, done: bool = False, reward: float = 0.0, message: str = "") -> WarehouseObservation:
        return WarehouseObservation(
            done=done,
            reward=reward,
            robot_pos=self._state.robot_pos,
            items_left=self._state.items,
            obstacles=self._state.obstacles,
            inventory=self._state.inventory,
            message=message,
            render=self.render()
        )
