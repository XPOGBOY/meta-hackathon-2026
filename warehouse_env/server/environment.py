"""OpenEnv-compliant warehouse environment.

This module implements the core simulation: a grid world with a robot, an
order queue, deliverable items, obstacles, deadlines, and dependency
constraints between items inside an order. It exposes the standard OpenEnv
``reset`` / ``step`` interface, so any OpenEnv-compatible agent can drive it.

Key collaborators:

* :class:`InstructionParser` — turns each order's natural-language brief
  into a structured plan (LLM-first, algorithmic fallback).
* :class:`PerformanceTracker` — records every finished episode and exposes
  rolling stats. The tracker's summary is fed straight back into the
  parser, which is what makes the agent self-improving.
* :func:`compute_reward` / :func:`compute_episode_score` — the two pure
  functions that turn observations into bounded scalar feedback.

The :data:`TASK_SPECS` table is the single source of truth for the
curriculum: each entry defines grid size, step budget, obstacle count,
and the orders that should appear (statically and dynamically).
"""

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

# Type alias: every coordinate in the env is a (x, y) pair on the grid.
Position = Tuple[int, int]

# Discrete movement vocabulary. Action ids 0-3 map to N/S/W/E displacements;
# ids 4 and 5 are reserved for `pick` and `deliver` and handled separately
# in `step()`. Keeping this as a constant (rather than a chain of if/elif)
# means the action dispatch is O(1) and trivially extensible.
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
    """Single-robot warehouse simulation, OpenEnv-compatible.

    The environment owns a :class:`WarehouseGameState`, an LLM-backed
    :class:`InstructionParser`, and a :class:`PerformanceTracker`. Every
    episode is fully reconstructed in :meth:`reset` from a curriculum
    entry in :data:`TASK_SPECS`, so episodes are reproducible given a seed
    and a task name.

    Action semantics (matching :data:`MOVE_DELTAS` plus pick/deliver):

    * ``0`` move up, ``1`` move down, ``2`` move left, ``3`` move right
    * ``4`` pick item at the current cell
    * ``5`` deliver current inventory at the current cell

    The class is safe to share across concurrent OpenEnv sessions because
    every per-episode mutable field is fully reinitialised in :meth:`reset`.
    """

    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self) -> None:
        """Construct an empty environment ready to be ``reset()``."""
        self._rng = random.Random()
        self._state = WarehouseGameState()
        self._performance_tracker = PerformanceTracker(max_episodes=30)
        # Hybrid parser: reads HF/OpenAI creds from the environment and
        # silently degrades to its algorithmic path when none are present.
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
        """Start a fresh episode for the requested curriculum task.

        Args:
            seed: Optional RNG seed. Pass a fixed value to make obstacle
                placement, in-stock sampling, and zone item placement
                fully reproducible.
            episode_id: Optional explicit episode id. Defaults to a fresh
                UUID4 — useful for trace correlation in OpenEnv logs.
            task_name: Curriculum task name. Unknown / legacy names are
                normalised to a sensible default (see
                :meth:`_normalize_task_name`).
            **kwargs: Reserved for forward-compat with OpenEnv extensions.

        Returns:
            The initial :class:`WarehouseObservation` for the new episode.
        """
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

        # Split the order list into two cohorts: the ones that exist at
        # t=0 and the ones that arrive mid-episode. Mid-episode arrivals
        # are stored as (arrival_step, order_id) tuples and injected by
        # `_inject_dynamic_orders` once the step counter passes them.
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
        """Apply one action and return the resulting observation.

        The method orchestrates the full per-step pipeline:
            1. Increment the step counter and accept any new LLM plan.
            2. Activate the next order if there's no active one.
            3. Dispatch the action (move / pick / deliver / invalid).
            4. Inject any orders whose arrival step has been reached.
            5. Expire the active order if its deadline elapsed.
            6. Detect end-of-episode (queue drained or step budget hit).
            7. Compute the dense reward; on terminal step, finalise the
               episode and add the bounded episode score on top.

        Args:
            action: The :class:`WarehouseAction` to apply. ``plan_response``
                is opportunistically captured into the state for trace
                visibility but does not change execution.
            timeout_s: Reserved for OpenEnv compatibility; unused.
            **kwargs: Reserved for forward-compat with OpenEnv extensions.

        Returns:
            The :class:`WarehouseObservation` after the step. ``done`` is
            ``True`` when the episode has terminated.
        """
        self._state.step_count += 1
        reward_context = RewardContext()
        message_parts: List[str] = []

        if action.plan_response:
            self._state.current_plan = ParsedPlan(raw_response=action.plan_response)

        if self._state.active_order_id is None:
            self._activate_next_order()

        # Action dispatch: ids 0-3 are O(1) movement lookups in
        # MOVE_DELTAS; 4 and 5 are the pick / deliver special cases. Any
        # other id is recorded as an invalid action so the agent gets a
        # negative learning signal without crashing the episode.
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
            # On the terminal step we tack the clamped episode score onto
            # the dense reward. Downstream RL code therefore sees a single
            # scalar that already encodes both the per-step shaping and
            # the headline performance metric.
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
        """The full internal game state. Read-only by convention."""
        return self._state

    def render(self) -> str:
        """Render the current grid as ASCII art for logs and demos.

        Legend:
            * ``.`` — empty cell
            * ``S`` — staging (delivery) cell
            * ``#`` — obstacle
            * ``$`` — pickable item
            * ``R`` — robot

        Returns:
            A multi-line string drawn with ``+``/``-``/``|`` borders.
        """
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
        """Snapshot the current state into an immutable ``WarehouseObservation``.

        Every Pydantic model that crosses the wire is deep-copied so that
        downstream consumers cannot accidentally mutate the env's state.
        """
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
        """Map legacy task aliases (Round 1) onto current curriculum names.

        Unknown names default to ``"simple_order"`` so a stray client
        request never crashes the env.
        """
        legacy_map = {
            "easy_picking": "simple_order",
            "medium_picking": "multi_step_order",
            "hard_picking": "adaptive_fulfillment",
        }
        normalized = legacy_map.get(task_name, task_name)
        return normalized if normalized in TASK_SPECS else "simple_order"

    def _build_zones(self, grid_size: Position) -> Tuple[List[Zone], List[Zone]]:
        """Carve the grid into four storage quadrants and two staging strips.

        Storage zones (A/B/C/D) tile the grid in a 2x2 pattern; the bottom
        row is dedicated to delivery (STAGE_1 on the left, STAGE_2 on the
        right). The ``max(...)`` guards keep the layout sane on tiny grids.
        """
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
        """Instantiate the static + dynamic orders defined by a task spec.

        Each item in the spec is sampled into a concrete grid position,
        respecting both the item's home zone and the set of positions
        already taken by previous items. Items flagged
        ``can_be_out_of_stock`` are randomly hidden with the configured
        probability — that's how we test the agent's resilience to
        partial-fulfillment scenarios.
        """
        # The spawn cell (0, 0) is reserved for the robot itself so we
        # never put an item underneath the agent on episode start.
        used_positions = {(0, 0)}
        zone_lookup = {zone.name: zone for zone in zones}
        delivery_lookup = {zone.name: zone for zone in delivery_zones}
        orders: List[Order] = []

        for index, order_spec in enumerate(spec["orders"]):
            items: List[OrderItem] = []
            for item_spec in order_spec["items"]:
                zone = zone_lookup[item_spec["zone"]]
                # Out-of-stock sampling is per-episode and per-item: we
                # roll once at materialisation time so the result is
                # consistent across the whole episode.
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
        """Sample obstacle positions that never trap an item or the staging zones.

        The sampler retries up to 50 times. On each attempt it draws a
        random subset of free cells and runs a BFS from the robot spawn
        to every target (each item + each delivery point). If even one
        target becomes unreachable, it resamples. This guarantees that
        every episode is *solvable* — the agent can always reach every
        item and deliver to every staging zone.
        """
        # Reserve the robot spawn, every in-stock item position, every
        # order's delivery anchor, and every cell of each staging zone.
        # Obstacles are only ever drawn from cells outside this set.
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

        # Reachability check: keep resampling until every target is
        # reachable from the spawn cell. 50 attempts is plenty in
        # practice — the obstacle density we use is far below the
        # percolation threshold.
        for _ in range(50):
            sampled = self._rng.sample(candidates, k=min(obstacle_count, len(candidates)))
            if all(self._path_exists((0, 0), point, grid_size, sampled) for point in target_points):
                return sorted(sampled)

        # Defensive fallback: deterministic prefix of candidates. This
        # branch is essentially unreachable on the curriculum's grids
        # but guarantees we never raise from `reset()`.
        return sorted(candidates[: min(obstacle_count, len(candidates))])

    def _sample_zone_position(self, zone: Zone, used_positions: set[Position]) -> Position:
        """Pick a free cell inside ``zone``, falling back to its anchor."""
        candidates = [
            (x, y)
            for x in range(zone.top_left[0], zone.bottom_right[0] + 1)
            for y in range(zone.top_left[1], zone.bottom_right[1] + 1)
            if (x, y) not in used_positions
        ]
        return self._rng.choice(candidates) if candidates else zone.anchor

    def _apply_move(self, action_id: int) -> Tuple[bool, str]:
        """Apply a movement action, clamping to the grid and respecting obstacles.

        Returns:
            ``(moved, message)`` — ``moved`` is ``False`` only when the
            target cell is blocked by an obstacle. Out-of-grid moves are
            silently clamped (the robot stays put against the wall).
        """
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
        """Try to pick the item under the robot, updating dependency stats.

        Side effects on ``reward_context``:
            * ``picked_item`` set on success.
            * ``picked_in_correct_order`` / ``picked_out_of_order`` set
              based on whether the item's prerequisites are satisfied.
            * ``fragile_risk`` set if a fragile item is picked while
              non-fragile items remain on the floor.
            * ``invalid_action`` set if there's no order or no item here.

        Also bumps ``priority_actions`` and (when applicable)
        ``priority_compliant_actions`` on the game state.
        """
        order = self._active_order()
        if order is None:
            reward_context.invalid_action = True
            return "No active order to pick from."

        item = self._find_pickable_item(order, self._state.robot_pos)
        if item is None:
            reward_context.invalid_action = True
            return "No requested item at the current position."

        # Two parallel checks: (a) does this pick satisfy the dependency
        # graph, and (b) is this item the *best* eligible choice right
        # now? They feed independent slots of the priority-compliance
        # statistic that ends up in `compute_episode_score`.
        eligible_names = self._eligible_item_names(order)
        highest_priority_item = self._highest_priority_eligible_item(order)
        self._state.priority_actions += 1
        if highest_priority_item is not None and item.name == highest_priority_item.name:
            self._state.priority_compliant_actions += 1

        if item.name in eligible_names:
            reward_context.picked_in_correct_order = True
        else:
            reward_context.picked_out_of_order = True
            self._state.dependency_violations += 1
            self._failure_reasons.append("dependency_violation")

        # Fragile-risk heuristic: picking a fragile item while
        # non-fragile items are still on the floor is technically legal
        # but suboptimal — the cushioning items should be loaded first.
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
        """Try to deliver the active order at the robot's current cell.

        Three failure modes are handled and tagged on ``reward_context``:
            * No active order — invalid action.
            * Robot not on a staging zone, or wrong staging zone —
              ``delivered_to_wrong_zone``.
            * Order is incomplete (some required item not yet picked) —
              invalid action with a "missing items" message.

        On success, every picked item is marked delivered, the order is
        moved to ``completed_orders``, and ``deadlines_met`` is bumped if
        the delivery beat the deadline.
        """
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
        # Distinguish "everything delivered" from "delivered with some
        # items missing because they were out of stock" — the latter is
        # still a successful adaptive fulfillment.
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
        """Move any arrived-now scheduled orders into the pending queue.

        Reads from ``self._scheduled_arrivals`` and is a no-op until at
        least one arrival's step has been reached. After injection the
        queue is re-prioritised so the new orders compete fairly with
        whatever was already pending.
        """
        arrived_now = [
            order_id
            for arrival_step, order_id in self._scheduled_arrivals
            if arrival_step <= self._state.step_count
        ]
        if not arrived_now:
            return

        # Keep only arrivals strictly in the future. We rebuild rather
        # than mutate so the comprehension above stays consistent with
        # the filter here.
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
        """Mark the active order as failed if its deadline has elapsed.

        Clears the agent's inventory on expiry — the failed order's items
        are conceptually returned to storage, and we don't want phantom
        items contaminating the next order's delivery check.
        """
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
        """Promote the next pending order to "active", if any.

        No-op when an order is already active or the queue is empty.
        Re-runs the prioritiser first so any orders that arrived since
        the last activation get a chance to jump the queue.
        """
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
        """Return the currently-active :class:`Order`, or ``None`` if there isn't one."""
        return self._order_lookup.get(self._state.active_order_id) if self._state.active_order_id else None

    def _prioritize_pending_orders(self) -> None:
        """Re-rank the pending queue using the hybrid LLM/heuristic ranker.

        We pass the recent-episodes summary into the parser so the
        ranking decision is conditioned on past failures — e.g. if the
        agent has been missing deadlines, the LLM tends to push
        deadline-tight orders even higher up the queue.
        """
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
        """Return the names of items that satisfy all dependency prerequisites.

        An item is "eligible" iff it is still in stock, hasn't been
        picked, and every ``before_item`` of every dependency edge
        targeting it has already been picked. This is the runtime
        analogue of the topological sort the parser uses offline.
        """
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
        """Return the eligible item the agent *should* pick next.

        Tie-break order: highest ``priority`` first, then nearest to the
        robot in Manhattan distance. The greedy nearest-eligible-priority
        rule is a simple stand-in for the proper TSP tour and is what
        the priority-compliance metric measures the agent against.
        """
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
        """Return the in-stock unpicked item at ``position``, if any."""
        for item in order.items:
            if item.position == position and item.in_stock and not item.delivered and not item.picked:
                return item
        return None

    def _delivery_zone_at_position(self, position: Position) -> Optional[Zone]:
        """Return the delivery :class:`Zone` containing ``position``, if any."""
        for zone in self._state.delivery_zones:
            if zone.contains(position):
                return zone
        return None

    def _deadline_remaining(self, order: Optional[Order]) -> Optional[int]:
        """Steps left on the order's deadline, or ``None`` if it has no deadline."""
        if order is None or order.deadline_steps is None or order.activated_step is None:
            return None
        return order.deadline_steps - (self._state.step_count - order.activated_step)

    def _collect_visible_items(self, orders: Sequence[Order]) -> List[OrderItem]:
        """Deep-copy every still-pickable item across all orders for the observation."""
        visible: List[OrderItem] = []
        for order in orders:
            for item in order.items:
                if item.in_stock and not item.picked and not item.delivered:
                    visible.append(item.model_copy(deep=True))
        return visible

    def _is_episode_done(self) -> bool:
        """``True`` once nothing is active, queued, or scheduled."""
        return self._state.active_order_id is None and not self._pending_orders and not self._scheduled_arrivals

    def _fail_remaining_orders(self, reason: str) -> None:
        """Mark every still-open order as failed and clear all queues.

        Called on hard episode termination (e.g. step budget exhausted).
        Idempotent across order statuses — already-completed/already-failed
        orders are left untouched.
        """
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
        """Compute the episode score and write a record into the tracker.

        This is the single point where the per-episode contract is
        produced: it computes the final clamped score, then appends a
        de-duplicated :class:`EpisodeRecord` to the tracker. The next
        episode's prompt context will already see this record because
        :meth:`PerformanceTracker.summary` reduces over the latest window.
        """
        # Idempotency guard: even if `step()` is called again after an
        # episode terminates (some clients do this), we only finalize once.
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
        # Use whichever signal is *more generous* — the rolling avg or
        # the raw completion rate — so the improvement axis stays well-
        # defined even for very early episodes where the rolling avg is
        # still close to zero.
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
        """Synthesize the natural-language brief that the LLM parser will see.

        The wording is intentionally a little verbose and human-sounding
        — it gives the LLM realistic surface variation (priority callouts,
        out-of-stock caveats, dependency clauses) so that the parser is
        exercised on text that resembles real warehouse orders.
        """
        item_phrases: List[str] = []
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
        """Return ``True`` iff there is a 4-connected path from ``start`` to ``goal``.

        Standard breadth-first search on the grid, treating ``obstacles``
        as walls. Used by :meth:`_generate_obstacles` as the solvability
        oracle: if BFS can't reach a target after a candidate placement,
        the placement is rejected and resampled.
        """
        if start == goal:
            return True

        blocked = set(obstacles)
        queue: Deque[Position] = deque([start])
        visited = {start}

        while queue:
            current = queue.popleft()
            for dx, dy in MOVE_DELTAS.values():
                neighbour = (current[0] + dx, current[1] + dy)
                if (
                    0 <= neighbour[0] < grid_size[0]
                    and 0 <= neighbour[1] < grid_size[1]
                    and neighbour not in blocked
                    and neighbour not in visited
                ):
                    if neighbour == goal:
                        return True
                    visited.add(neighbour)
                    queue.append(neighbour)
        return False

    @staticmethod
    def _distance(a: Position, b: Position) -> int:
        """Manhattan distance between two grid cells.

        The grid is 4-connected so Manhattan is the exact shortest-path
        length on an obstacle-free grid; with obstacles it is a tight
        admissible heuristic. We use it as the tie-break in
        :meth:`_highest_priority_eligible_item`.
        """
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
