from typing import List, Tuple, Optional
from openenv.core.env_server import Action, Observation, State

class WarehouseAction(Action):
    # 0: Up, 1: Down, 2: Left, 3: Right, 4: Pick
    # TODO: maybe add a \"drop\" action later?
    action_id: int

class WarehouseObservation(Observation):
    robot_pos: Tuple[int, int]
    items_left: List[Tuple[int, int]]
    obstacles: List[Tuple[int, int]]
    inventory: int
    message: str
    render: str

class WarehouseGameState(State):
    grid_size: Tuple[int, int] = (10, 10)
    robot_pos: Tuple[int, int] = (0, 0)
    items: List[Tuple[int, int]] = []
    obstacles: List[Tuple[int, int]] = []
    inventory: int = 0
    max_steps: int = 100
