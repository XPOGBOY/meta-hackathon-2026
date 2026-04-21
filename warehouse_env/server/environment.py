from __future__ import annotations

import random
import uuid
from collections import deque
from typing import Deque, Dict, List, Optional, Sequence, Tuple

from openenv.core.env_server import Environment

from warehouse_env.instruction_parser import InstructionParser
from warehouse_env.models import (
    Order,
    OrderDependency,
    OrderItem,
    ParsedPlan,
    WarehouseAction,
    WarehouseGameState,
    WarehouseObservation,
    Zone,
)
from warehouse_env.reward import RewardContext, clamp_score, compute_episode_score, compute_reward
from warehouse_env.self_improve import EpisodeRecord, PerformanceTracker

Position = Tuple[int, int]

MOVE_DELTAS: Dict[int, Position] = {
    0: (0, -1),
    1: (0, 1),
    2: (-1, 0),
    3: (1, 0),
}


TASK_SPECS: Dict[str, Dict[str, object]] = {
    "simple_order": {
        "grid_size": (5, 5),
        "max_steps": 45,
        "obstacle_count": 1,
        "initial_orders": 1,
        "arrival_steps": [],
        "orders": [
            {
                "delivery_zone": "STAGE_1",
                "deadline_steps": 20,
                "items": [
                    {"name": "scanner_crate", "zone": "A", "priority": 5},
                    {"name": "label_roll", "zone": "B", "priority": 2},
                ],
                "dependencies": [],
            }
        ],
    },
    "multi_step_order": {
        "grid_size": (10, 10),
        "max_steps": 100,
        "obstacle_count": 6,
        "initial_orders": 1,
        "arrival_steps": [],
        "orders": [
            {
                "delivery_zone": "STAGE_2",
                "deadline_steps": 36,
                "items": [
                    {"name": "electronics_tote", "zone": "A", "priority": 5},
                    {"name": "control_board", "zone": "D", "priority": 4},
                    {"name": "foam_insert", "zone": "C", "priority": 3},
                    {"name": "fragile_sensor", "zone": "B", "priority": 4, "is_fragile": True},
                ],
                "dependencies": [
                    ("electronics_tote", "control_board"),
                    ("foam_insert", "fragile_sensor"),
                    ("control_board", "fragile_sensor"),
                ],
            }
        ],
    },
    "order_queue": {
        "grid_size": (10, 10),
        "max_steps": 120,
        "obstacle_count": 7,
        "initial_orders": 3,
        "arrival_steps": [],
        "orders": [
            {
                "delivery_zone": "STAGE_1",
                "deadline_steps": 26,
                "items": [
                    {"name": "priority_router", "zone": "D", "priority": 5},
                    {"name": "packing_slips", "zone": "C", "priority": 2},
                ],
                "dependencies": [],
            },
            {
                "delivery_zone": "STAGE_2",
                "deadline_steps": 32,
                "items": [
                    {"name": "camera_body", "zone": "A", "priority": 4},
                    {"name": "lens_case", "zone": "B", "priority": 3, "is_fragile": True},
                    {"name": "foam_sheet", "zone": "C", "priority": 2},
                ],
                "dependencies": [("foam_sheet", "lens_case")],
            },
            {
                "delivery_zone": "STAGE_1",
                "deadline_steps": 30,
                "items": [
                    {"name": "audit_tag", "zone": "B", "priority": 3},
                    {"name": "battery_pack", "zone": "D", "priority": 4},
                    {"name": "safety_wrap", "zone": "C", "priority": 2},
                ],
                "dependencies": [("battery_pack", "audit_tag")],
            },
        ],
    },
    "adaptive_fulfillment": {
        "grid_size": (15, 15),
        "max_steps": 180,
        "obstacle_count": 16,
        "initial_orders": 2,
        "arrival_steps": [8, 15, 24],
        "orders": [
            {
                "delivery_zone": "STAGE_1",
                "deadline_steps": 34,
                "items": [
                    {"name": "expedite_console", "zone": "A", "priority": 5},
                    {"name": "shock_absorber", "zone": "C", "priority": 3},
                    {"name": "fragile_display", "zone": "B", "priority": 4, "is_fragile": True},
                ],
                "dependencies": [("shock_absorber", "fragile_display")],
            },
            {
                "delivery_zone": "STAGE_2",
                "deadline_steps": 28,
                "items": [
                    {"name": "rush_router", "zone": "D", "priority": 5},
                    {"name": "warranty_packet", "zone": "C", "priority": 2},
                ],
                "dependencies": [],
            },
            {
                "delivery_zone": "STAGE_1",
                "deadline_steps": 26,
                "items": [
                    {
                        "name": "medical_vial_box",
                        "zone": "B",
                        "priority": 4,
                        "is_fragile": True,
                        "can_be_out_of_stock": True,
                        "out_of_stock_probability": 0.55,
                    },
                    {"name": "sterile_wrap", "zone": "C", "priority": 3},
                    {"name": "tracking_beacon", "zone": "A", "priority": 4},
                ],
                "dependencies": [("sterile_wrap", "medical_vial_box")],
            },
            {
                "delivery_zone": "STAGE_2",
                "deadline_steps": 24,
                "items": [
                    {"name": "premium_gpu", "zone": "A", "priority": 5},
                    {"name": "inspection_tag", "zone": "D", "priority": 2},
                ],
                "dependencies": [],
            },
            {
                "delivery_zone": "STAGE_1",
                "deadline_steps": 30,
                "items": [
                    {"name": "fragile_camera", "zone": "B", "priority": 4, "is_fragile": True},
                    {"name": "foam_cradle", "zone": "C", "priority": 3},
                    {"name": "signature_form", "zone": "D", "priority": 1},
                ],
                "dependencies": [("foam_cradle", "fragile_camera")],
            },
        ],
    },
}


class WarehouseEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self):
        self._rng = random.Random()
        self._state = WarehouseGameState()
        self._performance_tracker = PerformanceTracker(max_episodes=30)
        self._instruction_parser = InstructionParser.from_env()
        self._pending_orders: Deque[str] = deque()
        self._scheduled_arrivals: List[Tuple[int, str]] = []
        self._order_lookup: Dict[str, Order] = {}
        self._episode_finalized = False
        self._failure_reasons: List[str] = []

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        task_name: Optional[str] = None,
        **kwargs,
    ) -> WarehouseObservation:
        canonical_task = self._normalize_task_name(task_name or "simple_order")
        spec = TASK_SPECS[canonical_task]

        if seed is not None:
            self._rng.seed(seed)

        grid_size = spec["grid_size"]
        max_steps = spec["max_steps"]
        zones, delivery_zones = self._build_zones(grid_size)
        orders = self._materialize_orders(canonical_task, spec, zones, delivery_zones)
        obstacles = self._generate_obstacles(
            grid_size=grid_size,
            obstacle_count=int(spec["obstacle_count"]),
            orders=orders,
            delivery_zones=delivery_zones,
        )

        self._pending_orders = deque()
        self._scheduled_arrivals = []
        self._order_lookup = {order.order_id: order for order in orders}
        self._episode_finalized = False
        self._failure_reasons = []

        initial_orders = int(spec["initial_orders"])
        arrival_steps = list(spec["arrival_steps"])
        for index, order in enumerate(orders):
            if index < initial_orders:
                self._pending_orders.append(order.order_id)
            else:
                arrival_step = arrival_steps[index - initial_orders]
                self._scheduled_arrivals.append((arrival_step, order.order_id))

        self._prioritize_pending_orders()

        self._state = WarehouseGameState(
            episode_id=episode_id or str(uuid.uuid4()),
            task_name=canonical_task,
            step_count=0,
            grid_size=grid_size,
            robot_pos=(0, 0),
            items=self._collect_visible_items(orders),
            obstacles=obstacles,
            inventory=[],
            max_steps=max_steps,
            zones=zones,
            delivery_zones=delivery_zones,
            orders=orders,
            active_order_id=None,
            completed_orders=[],
            failed_orders=[],
            current_plan=None,
            score=0.0001,
            total_reward=0.0,
            priority_actions=0,
            priority_compliant_actions=0,
            dependency_violations=0,
            deadlines_met=0,
            total_orders_expected=len(orders),
        )

        self._activate_next_order()
        return self._make_observation(message=f"Starting task {canonical_task}.")

    def step(
        self,
        action: WarehouseAction,
        timeout_s: Optional[float] = None,
        **kwargs,
    ) -> WarehouseObservation:
        self._state.step_count += 1
        reward_context = RewardContext()
        message_parts: List[str] = []

        if action.plan_response:
            self._state.current_plan = ParsedPlan(raw_response=action.plan_response)

        if self._state.active_order_id is None:
            self._activate_next_order()

        if action.action_id in MOVE_DELTAS:
            moved, move_message = self._apply_move(action.action_id)
            if not moved:
                reward_context.obstacle_collision = True
            message_parts.append(move_message)
        elif action.action_id == 4:
            message_parts.append(self._apply_pick(reward_context))
        elif action.action_id == 5:
            message_parts.append(self._apply_deliver(reward_context))
        else:
            reward_context.invalid_action = True
            message_parts.append(f"Invalid action id: {action.action_id}.")

        self._inject_dynamic_orders(message_parts)
        self._expire_deadline_if_needed(reward_context, message_parts)

        if self._state.active_order_id is None:
            self._activate_next_order()

        done = self._is_episode_done()
        if self._state.step_count >= self._state.max_steps:
            done = True
            self._fail_remaining_orders("max_steps")
            message_parts.append("Episode ended because max steps were reached.")

        reward = compute_reward(self._state, action.action_id, reward_context)
        if done:
            self._finalize_episode()
            reward += self._state.score
            message_parts.append(f"Episode complete. Final score {self._state.score:.4f}.")

        self._state.total_reward += reward
        self._state.items = self._collect_visible_items(self._state.orders)

        return self._make_observation(
            done=done,
            reward=reward,
            message=" ".join(part for part in message_parts if part).strip(),
        )

    @property
    def state(self) -> WarehouseGameState:
        return self._state

    def render(self) -> str:
        width, height = self._state.grid_size
        grid = [["." for _ in range(width)] for _ in range(height)]

        for zone in self._state.delivery_zones:
            for x in range(zone.top_left[0], zone.bottom_right[0] + 1):
                for y in range(zone.top_left[1], zone.bottom_right[1] + 1):
                    grid[y][x] = "S"

        for ox, oy in self._state.obstacles:
            grid[oy][ox] = "#"

        for item in self._state.items:
            if item.in_stock and not item.picked and not item.delivered:
                x, y = item.position
                grid[y][x] = "$"

        rx, ry = self._state.robot_pos
        grid[ry][rx] = "R"

        lines = ["+ " + "- " * width + "+"]
        for row in grid:
            lines.append("| " + " ".join(row) + " |")
        lines.append("+ " + "- " * width + "+")
        return "\n".join(lines)

    def _make_observation(
        self,
        done: bool = False,
        reward: float = 0.0,
        message: str = "",
    ) -> WarehouseObservation:
        current_order = self._active_order()
        visible_items = self._collect_visible_items(self._state.orders)
        return WarehouseObservation(
            done=done,
            reward=reward,
            robot_pos=self._state.robot_pos,
            visible_items=visible_items,
            items_left=[
                item.position
                for item in visible_items
                if item.in_stock and not item.picked
            ],
            obstacles=self._state.obstacles,
            inventory=[item.model_copy(deep=True) for item in self._state.inventory],
            inventory_count=len(self._state.inventory),
            current_order=current_order.model_copy(deep=True) if current_order else None,
            order_queue_size=len(self._pending_orders),
            delivery_zones=[zone.model_copy(deep=True) for zone in self._state.delivery_zones],
            deadline_remaining=self._deadline_remaining(current_order),
            episode_history_summary=self._performance_tracker.summary(),
            message=message,
            render=self.render(),
        )

    def _normalize_task_name(self, task_name: str) -> str:
        legacy_map = {
            "easy_picking": "simple_order",
            "medium_picking": "multi_step_order",
            "hard_picking": "adaptive_fulfillment",
        }
        normalized = legacy_map.get(task_name, task_name)
        return normalized if normalized in TASK_SPECS else "simple_order"

    def _build_zones(self, grid_size: Position) -> Tuple[List[Zone], List[Zone]]:
        width, height = grid_size
        mid_x = width // 2
        mid_y = height // 2

        zones = [
            Zone(name="A", top_left=(1, 1), bottom_right=(max(1, mid_x - 1), max(1, mid_y - 1))),
            Zone(name="B", top_left=(mid_x, 1), bottom_right=(max(mid_x, width - 2), max(1, mid_y - 1))),
            Zone(name="C", top_left=(1, mid_y), bottom_right=(max(1, mid_x - 1), max(mid_y, height - 2))),
            Zone(name="D", top_left=(mid_x, mid_y), bottom_right=(max(mid_x, width - 2), max(mid_y, height - 2))),
        ]
        delivery_zones = [
            Zone(
                name="STAGE_1",
                top_left=(0, height - 1),
                bottom_right=(min(1, width - 1), height - 1),
                zone_type="delivery",
            ),
            Zone(
                name="STAGE_2",
                top_left=(max(width - 2, 0), height - 1),
                bottom_right=(width - 1, height - 1),
                zone_type="delivery",
            ),
        ]
        return zones, delivery_zones

    def _materialize_orders(
        self,
        task_name: str,
        spec: Dict[str, object],
        zones: Sequence[Zone],
        delivery_zones: Sequence[Zone],
    ) -> List[Order]:
        used_positions = {(0, 0)}
        zone_lookup = {zone.name: zone for zone in zones}
        delivery_lookup = {zone.name: zone for zone in delivery_zones}
        orders: List[Order] = []

        for index, order_spec in enumerate(spec["orders"]):
            items: List[OrderItem] = []
            for item_spec in order_spec["items"]:
                zone = zone_lookup[item_spec["zone"]]
                in_stock = not (
                    item_spec.get("can_be_out_of_stock")
                    and self._rng.random() < item_spec.get("out_of_stock_probability", 0.0)
                )
                position = self._sample_zone_position(zone, used_positions) if in_stock else (-1, -1)
                if in_stock:
                    used_positions.add(position)
                items.append(
                    OrderItem(
                        name=item_spec["name"],
                        position=position,
                        zone=item_spec["zone"],
                        is_fragile=bool(item_spec.get("is_fragile", False)),
                        priority=int(item_spec.get("priority", 3)),
                        in_stock=in_stock,
                    )
                )

            delivery_zone = delivery_lookup[order_spec["delivery_zone"]]
            orders.append(
                Order(
                    order_id=f"{task_name}-{index + 1}",
                    instruction_text=self._build_instruction_text(
                        items=items,
                        delivery_zone=delivery_zone.name,
                        dependencies=order_spec["dependencies"],
                    ),
                    items=items,
                    delivery_zone=delivery_zone.name,
                    delivery_position=delivery_zone.anchor,
                    dependencies=[
                        OrderDependency(before_item=before, after_item=after)
                        for before, after in order_spec["dependencies"]
                    ],
                    deadline_steps=order_spec.get("deadline_steps"),
                    status="pending",
                )
            )

        return orders

    def _generate_obstacles(
        self,
        *,
        grid_size: Position,
        obstacle_count: int,
        orders: Sequence[Order],
        delivery_zones: Sequence[Zone],
    ) -> List[Position]:
        reserved = {(0, 0)}
        for order in orders:
            reserved.add(order.delivery_position)
            for item in order.items:
                if item.in_stock:
                    reserved.add(item.position)
        for zone in delivery_zones:
            for x in range(zone.top_left[0], zone.bottom_right[0] + 1):
                for y in range(zone.top_left[1], zone.bottom_right[1] + 1):
                    reserved.add((x, y))

        candidates = [
            (x, y)
            for x in range(grid_size[0])
            for y in range(grid_size[1])
            if (x, y) not in reserved
        ]
        target_points = [order.delivery_position for order in orders] + [
            item.position for order in orders for item in order.items if item.in_stock
        ]

        for _ in range(50):
            sampled = self._rng.sample(candidates, k=min(obstacle_count, len(candidates)))
            if all(self._path_exists((0, 0), point, grid_size, sampled) for point in target_points):
                return sorted(sampled)

        return sorted(candidates[: min(obstacle_count, len(candidates))])

    def _sample_zone_position(self, zone: Zone, used_positions: set[Position]) -> Position:
        candidates = [
            (x, y)
            for x in range(zone.top_left[0], zone.bottom_right[0] + 1)
            for y in range(zone.top_left[1], zone.bottom_right[1] + 1)
            if (x, y) not in used_positions
        ]
        return self._rng.choice(candidates) if candidates else zone.anchor

    def _apply_move(self, action_id: int) -> Tuple[bool, str]:
        dx, dy = MOVE_DELTAS[action_id]
        width, height = self._state.grid_size
        next_pos = (
            min(max(self._state.robot_pos[0] + dx, 0), width - 1),
            min(max(self._state.robot_pos[1] + dy, 0), height - 1),
        )
        if next_pos in self._state.obstacles:
            return False, f"Blocked by obstacle at {next_pos}."
        self._state.robot_pos = next_pos
        return True, f"Moved to {next_pos}."

    def _apply_pick(self, reward_context: RewardContext) -> str:
        order = self._active_order()
        if order is None:
            reward_context.invalid_action = True
            return "No active order to pick from."

        item = self._find_pickable_item(order, self._state.robot_pos)
        if item is None:
            reward_context.invalid_action = True
            return "No requested item at the current position."

        eligible_names = self._eligible_item_names(order)
        highest_priority = self._highest_priority_eligible_item(order)
        self._state.priority_actions += 1
        if highest_priority is not None and item.name == highest_priority.name:
            self._state.priority_compliant_actions += 1

        if item.name in eligible_names:
            reward_context.picked_in_correct_order = True
        else:
            reward_context.picked_out_of_order = True
            self._state.dependency_violations += 1
            self._failure_reasons.append("dependency_violation")

        if item.is_fragile:
            non_fragile_unpicked = [
                other
                for other in order.items
                if not other.is_fragile and not other.picked and other.in_stock
            ]
            if non_fragile_unpicked:
                reward_context.fragile_risk = True

        item.picked = True
        self._state.inventory.append(item)
        reward_context.picked_item = item
        return f"Picked {item.name} from zone {item.zone}."

    def _apply_deliver(self, reward_context: RewardContext) -> str:
        order = self._active_order()
        if order is None:
            reward_context.invalid_action = True
            return "No active order to deliver."

        delivery_zone = self._delivery_zone_at_position(self._state.robot_pos)
        if delivery_zone is None:
            reward_context.delivered_to_wrong_zone = True
            self._failure_reasons.append("delivery_error")
            return "Deliver action used outside a staging zone."

        if delivery_zone.name != order.delivery_zone:
            reward_context.delivered_to_wrong_zone = True
            self._failure_reasons.append("delivery_error")
            return f"Wrong delivery zone. Expected {order.delivery_zone}, found {delivery_zone.name}."

        required_items = [item for item in order.items if item.in_stock]
        missing_items = [item.name for item in required_items if not item.picked]
        if missing_items:
            reward_context.invalid_action = True
            self._failure_reasons.append("delivery_error")
            return f"Cannot deliver yet. Missing items: {', '.join(missing_items)}."

        for item in order.items:
            if item.picked:
                item.delivered = True

        self._state.inventory = []
        order.completion_step = self._state.step_count
        order.status = "completed_with_fallback" if any(not item.in_stock for item in order.items) else "completed"
        self._state.completed_orders.append(order.order_id)
        self._state.active_order_id = None
        reward_context.delivered_to_correct_zone = True
        reward_context.order_fully_completed = True

        remaining = self._deadline_remaining(order)
        if remaining is not None:
            reward_context.remaining_steps = max(0, remaining)
            reward_context.total_deadline = order.deadline_steps or 1
        if remaining is None or remaining >= 0:
            reward_context.completed_before_deadline = True
            self._state.deadlines_met += 1

        return f"Delivered order {order.order_id} to {order.delivery_zone}."

    def _inject_dynamic_orders(self, message_parts: List[str]) -> None:
        arrived_now = [
            order_id
            for arrival_step, order_id in self._scheduled_arrivals
            if arrival_step <= self._state.step_count
        ]
        if not arrived_now:
            return

        self._scheduled_arrivals = [
            (arrival_step, order_id)
            for arrival_step, order_id in self._scheduled_arrivals
            if arrival_step > self._state.step_count
        ]

        for order_id in arrived_now:
            order = self._order_lookup[order_id]
            order.status = "pending"
            self._pending_orders.append(order_id)
        self._prioritize_pending_orders()
        message_parts.append(f"{len(arrived_now)} new order(s) joined the queue.")

    def _expire_deadline_if_needed(
        self,
        reward_context: RewardContext,
        message_parts: List[str],
    ) -> None:
        order = self._active_order()
        remaining = self._deadline_remaining(order)
        if order is None or remaining is None or remaining >= 0:
            return

        reward_context.remaining_steps = max(0, remaining)
        reward_context.total_deadline = order.deadline_steps or 1
        reward_context.deadline_exceeded = True
        self._failure_reasons.append("deadline_missed")
        order.status = "failed_deadline"
        order.notes.append("Deadline exceeded before delivery.")
        self._state.failed_orders.append(order.order_id)
        self._state.inventory = []
        self._state.active_order_id = None
        message_parts.append(f"Order {order.order_id} failed because its deadline expired.")

    def _activate_next_order(self) -> None:
        if self._state.active_order_id is not None or not self._pending_orders:
            return
        self._prioritize_pending_orders()
        next_order_id = self._pending_orders.popleft()
        order = self._order_lookup[next_order_id]
        order.status = "active"
        if order.activated_step is None:
            order.activated_step = self._state.step_count
        self._state.active_order_id = next_order_id

    def _active_order(self) -> Optional[Order]:
        return self._order_lookup.get(self._state.active_order_id) if self._state.active_order_id else None

    def _prioritize_pending_orders(self) -> None:
        if len(self._pending_orders) <= 1:
            return

        pending_orders = [self._order_lookup[order_id] for order_id in self._pending_orders]
        ranked_ids = self._instruction_parser.rank_orders(
            pending_orders,
            episode_history_summary=self._performance_tracker.summary(),
        )
        if ranked_ids:
            self._pending_orders = deque(ranked_ids)

    def _eligible_item_names(self, order: Order) -> set[str]:
        picked_names = {item.name for item in order.items if item.picked}
        eligible: set[str] = set()
        for item in order.items:
            if item.picked or not item.in_stock:
                continue
            prerequisites = {
                dependency.before_item
                for dependency in order.dependencies
                if dependency.after_item == item.name
            }
            if prerequisites.issubset(picked_names):
                eligible.add(item.name)
        return eligible

    def _highest_priority_eligible_item(self, order: Order) -> Optional[OrderItem]:
        eligible_names = self._eligible_item_names(order)
        eligible_items = [
            item for item in order.items if item.name in eligible_names and item.in_stock and not item.picked
        ]
        if not eligible_items:
            return None
        return max(
            eligible_items,
            key=lambda item: (item.priority, -self._distance(self._state.robot_pos, item.position)),
        )

    def _find_pickable_item(self, order: Order, position: Position) -> Optional[OrderItem]:
        for item in order.items:
            if item.position == position and item.in_stock and not item.delivered and not item.picked:
                return item
        return None

    def _delivery_zone_at_position(self, position: Position) -> Optional[Zone]:
        for zone in self._state.delivery_zones:
            if zone.contains(position):
                return zone
        return None

    def _deadline_remaining(self, order: Optional[Order]) -> Optional[int]:
        if order is None or order.deadline_steps is None or order.activated_step is None:
            return None
        return order.deadline_steps - (self._state.step_count - order.activated_step)

    def _collect_visible_items(self, orders: Sequence[Order]) -> List[OrderItem]:
        visible: List[OrderItem] = []
        for order in orders:
            for item in order.items:
                if item.in_stock and not item.picked and not item.delivered:
                    visible.append(item.model_copy(deep=True))
        return visible

    def _is_episode_done(self) -> bool:
        return self._state.active_order_id is None and not self._pending_orders and not self._scheduled_arrivals

    def _fail_remaining_orders(self, reason: str) -> None:
        for order in self._state.orders:
            if order.status not in {"completed", "completed_with_fallback", "failed_deadline", "failed"}:
                order.status = "failed"
                order.notes.append(f"Order failed because {reason}.")
                if order.order_id not in self._state.failed_orders:
                    self._state.failed_orders.append(order.order_id)
        self._state.active_order_id = None
        self._pending_orders.clear()
        self._scheduled_arrivals.clear()
        self._state.inventory = []
        self._failure_reasons.append(reason)

    def _finalize_episode(self) -> None:
        if self._episode_finalized:
            return

        completed_orders = len(self._state.completed_orders)
        total_orders = max(self._state.total_orders_expected, 1)
        priority_compliance = (
            self._state.priority_compliant_actions / float(self._state.priority_actions)
            if self._state.priority_actions > 0
            else 1.0
        )
        efficiency_ratio = max(0.0, 1.0 - (self._state.step_count / float(max(self._state.max_steps, 1))))
        baseline_score = self._performance_tracker.baseline_score()
        current_average = max(
            self._performance_tracker.recent_average_score(),
            completed_orders / float(total_orders),
        )

        self._state.score = clamp_score(
            compute_episode_score(
                total_orders=total_orders,
                completed_orders=completed_orders,
                priority_actions=self._state.priority_actions,
                priority_compliant_actions=self._state.priority_compliant_actions,
                steps_taken=self._state.step_count,
                max_steps=self._state.max_steps,
                baseline_score=baseline_score,
                current_average_score=current_average,
            )
        )

        self._performance_tracker.record_episode(
            EpisodeRecord(
                task_name=self._state.task_name,
                score=self._state.score,
                steps_taken=self._state.step_count,
                orders_completed=completed_orders,
                total_orders=total_orders,
                failure_reasons=sorted(set(self._failure_reasons)),
                priority_compliance=priority_compliance,
                efficiency_ratio=efficiency_ratio,
            )
        )
        self._episode_finalized = True

    def _build_instruction_text(
        self,
        *,
        items: Sequence[OrderItem],
        delivery_zone: str,
        dependencies: Sequence[Tuple[str, str]],
    ) -> str:
        item_phrases = []
        for item in items:
            fragility = "fragile " if item.is_fragile else ""
            stock_note = " if available" if not item.in_stock else ""
            item_phrases.append(
                f"{fragility}{item.name} from zone {item.zone}{stock_note} (priority {item.priority})"
            )

        sentences = [
            "Fulfill this warehouse order.",
            "Collect " + ", then ".join(item_phrases) + ".",
            f"Deliver everything to {delivery_zone}.",
        ]
        if dependencies:
            sentences.append(
                "Respect dependencies: "
                + "; ".join(f"pick {before} before {after}" for before, after in dependencies)
                + "."
            )
        high_priority_items = [item.name for item in items if item.priority >= 4]
        if high_priority_items:
            sentences.append("Prioritize " + ", ".join(high_priority_items) + ".")
        if any(not item.in_stock for item in items):
            sentences.append("If an item is out of stock, continue with the rest and deliver the partial order.")
        return " ".join(sentences)

    def _path_exists(
        self,
        start: Position,
        goal: Position,
        grid_size: Position,
        obstacles: Sequence[Position],
    ) -> bool:
        if start == goal:
            return True

        blocked = set(obstacles)
        queue = deque([start])
        visited = {start}

        while queue:
            current = queue.popleft()
            for dx, dy in MOVE_DELTAS.values():
                nxt = (current[0] + dx, current[1] + dy)
                if (
                    0 <= nxt[0] < grid_size[0]
                    and 0 <= nxt[1] < grid_size[1]
                    and nxt not in blocked
                    and nxt not in visited
                ):
                    if nxt == goal:
                        return True
                    visited.add(nxt)
                    queue.append(nxt)
        return False

    @staticmethod
    def _distance(a: Position, b: Position) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
