from __future__ import annotations

from typing import List, Optional, Tuple

from openenv.core.env_server import Action, Observation, State
from pydantic import BaseModel, Field

Position = Tuple[int, int]


class Zone(BaseModel):
    name: str
    top_left: Position
    bottom_right: Position
    zone_type: str = "storage"

    def contains(self, position: Position) -> bool:
        x, y = position
        return (
            self.top_left[0] <= x <= self.bottom_right[0]
            and self.top_left[1] <= y <= self.bottom_right[1]
        )

    @property
    def anchor(self) -> Position:
        return self.top_left


class OrderDependency(BaseModel):
    before_item: str
    after_item: str


class OrderItem(BaseModel):
    name: str
    position: Position
    zone: str
    is_fragile: bool = False
    priority: int = 3
    in_stock: bool = True
    picked: bool = False
    delivered: bool = False


class Order(BaseModel):
    order_id: str
    instruction_text: str
    items: List[OrderItem] = Field(default_factory=list)
    delivery_zone: str
    delivery_position: Position
    dependencies: List[OrderDependency] = Field(default_factory=list)
    deadline_steps: Optional[int] = None
    status: str = "pending"
    activated_step: Optional[int] = None
    completion_step: Optional[int] = None
    notes: List[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    action: str
    target: str
    zone: Optional[str] = None
    notes: str = ""


class ParsedPlan(BaseModel):
    ordered_item_names: List[str] = Field(default_factory=list)
    steps: List[PlanStep] = Field(default_factory=list)
    delivery_zone_name: Optional[str] = None
    priorities: List[str] = Field(default_factory=list)
    ambiguity_notes: List[str] = Field(default_factory=list)
    raw_response: Optional[str] = None


class WarehouseAction(Action):
    # 0: up, 1: down, 2: left, 3: right, 4: pick, 5: deliver
    action_id: int
    plan_response: Optional[str] = None


class WarehouseObservation(Observation):
    robot_pos: Position = (0, 0)
    visible_items: List[OrderItem] = Field(default_factory=list)
    items_left: List[Position] = Field(default_factory=list)
    obstacles: List[Position] = Field(default_factory=list)
    inventory: List[OrderItem] = Field(default_factory=list)
    inventory_count: int = 0
    current_order: Optional[Order] = None
    order_queue_size: int = 0
    delivery_zones: List[Zone] = Field(default_factory=list)
    deadline_remaining: Optional[int] = None
    episode_history_summary: str = ""
    message: str = ""
    render: str = ""


class WarehouseGameState(State):
    task_name: str = "simple_order"
    grid_size: Position = (10, 10)
    robot_pos: Position = (0, 0)
    items: List[OrderItem] = Field(default_factory=list)
    obstacles: List[Position] = Field(default_factory=list)
    inventory: List[OrderItem] = Field(default_factory=list)
    max_steps: int = 100
    zones: List[Zone] = Field(default_factory=list)
    delivery_zones: List[Zone] = Field(default_factory=list)
    orders: List[Order] = Field(default_factory=list)
    active_order_id: Optional[str] = None
    completed_orders: List[str] = Field(default_factory=list)
    failed_orders: List[str] = Field(default_factory=list)
    current_plan: Optional[ParsedPlan] = None
    score: float = 0.0001
    total_reward: float = 0.0
    priority_actions: int = 0
    priority_compliant_actions: int = 0
    dependency_violations: int = 0
    deadlines_met: int = 0
    total_orders_expected: int = 0
