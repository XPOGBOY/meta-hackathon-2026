"""Multi-robot coordination environment for the Meta PyTorch OpenEnv Hackathon 2026.

Two robots operate concurrently on a shared order queue.  Each robot has its
own position and inventory, but they share the same grid, the same obstacles,
and the same pool of orders.  A lightweight collision-avoidance penalty and a
coordination-efficiency bonus make it strictly better to keep the robots apart
and divide work than to have them shadow each other.

Usage (standalone test)::

    from warehouse_env.server.multi_robot_environment import MultiRobotWarehouse

    env = MultiRobotWarehouse(num_robots=2)
    obs = env.reset(task_name="simple_order")
    obs, reward, done = env.step({"R1": 3, "R2": 0})
"""

from __future__ import annotations

import random
import uuid
from collections import deque
from typing import Deque, Dict, List, Optional, Sequence, Set, Tuple

from warehouse_env.models import (
    Order,
    OrderDependency,
    OrderItem,
    WarehouseGameState,
    WarehouseObservation,
    Zone,
)
from warehouse_env.reward import RewardContext, clamp_score, compute_reward
from warehouse_env.server.environment import TASK_SPECS, WarehouseEnvironment

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Position = Tuple[int, int]
RobotId = str

MOVE_DELTAS: Dict[int, Position] = {
    0: (0, -1),   # up
    1: (0, 1),    # down
    2: (-1, 0),   # left
    3: (1, 0),    # right
}


# ---------------------------------------------------------------------------
# Robot
# ---------------------------------------------------------------------------

class Robot:
    """Lightweight per-robot state container."""

    def __init__(self, robot_id: RobotId, start_pos: Position) -> None:
        self.robot_id = robot_id
        self.pos: Position = start_pos
        self.inventory: List[OrderItem] = []
        self.steps_taken: int = 0
        self.assigned_order_id: Optional[str] = None
        self.collisions: int = 0

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def can_move_to(
        self,
        target: Position,
        obstacles: List[Position],
        grid_size: Position,
        other_robot_positions: List[Position],
    ) -> bool:
        """Return True if *target* is a reachable, unoccupied cell."""
        gw, gh = grid_size
        if not (0 <= target[0] < gw and 0 <= target[1] < gh):
            return False
        if target in obstacles:
            return False
        if target in other_robot_positions:
            return False
        return True

    def manhattan(self, target: Position) -> int:
        return abs(self.pos[0] - target[0]) + abs(self.pos[1] - target[1])


# ---------------------------------------------------------------------------
# MultiRobotWarehouse
# ---------------------------------------------------------------------------

class MultiRobotWarehouse:
    """Two-robot warehouse environment with shared order queue.

    The environment is intentionally *not* a subclass of
    ``WarehouseEnvironment`` because that class is single-robot by design.
    Instead we reuse its ``TASK_SPECS`` and ``Zone`` / ``OrderItem``
    data-model helpers, keeping the code DRY without fighting the parent API.

    Action space (per robot)
    ------------------------
    0  up  |  1  down  |  2  left  |  3  right  |  4  pick  |  5  deliver

    Observation
    -----------
    Each robot receives its own ``WarehouseObservation`` (same model used by
    the single-robot environment, so existing client code stays compatible).

    Episode score
    -------------
    ``score = completion_ratio * 0.50
            + coordination_efficiency * 0.25
            + collision_avoidance * 0.15
            + priority_compliance * 0.10``

    Clamped to [0.0001, 0.9999] for OpenEnv compatibility.
    """

    def __init__(self, num_robots: int = 2) -> None:
        if num_robots < 1:
            raise ValueError("num_robots must be >= 1")
        self.num_robots = num_robots

        self._rng = random.Random(42)
        self._robots: Dict[RobotId, Robot] = {}
        self._state: WarehouseGameState = WarehouseGameState()

        # Shared order queue
        self._order_lookup: Dict[str, Order] = {}
        self._pending_order_ids: Deque[str] = deque()
        self._completed_order_ids: List[str] = []
        self._failed_order_ids: List[str] = []

        # Episode-level counters
        self._collision_count: int = 0
        self._total_steps: int = 0
        self._priority_actions: int = 0
        self._priority_compliant_actions: int = 0
        self._episode_done: bool = False

        self._init_robots()

    # ------------------------------------------------------------------
    # Public API — mirrors WarehouseEnvironment interface where possible
    # ------------------------------------------------------------------

    def reset(self, task_name: str = "simple_order") -> Dict[RobotId, WarehouseObservation]:
        """Reset the environment and return per-robot initial observations."""
        canonical = self._normalize_task(task_name)
        spec = TASK_SPECS[canonical]

        self._state = WarehouseGameState(
            episode_id=str(uuid.uuid4()),
            task_name=canonical,
            grid_size=spec["grid_size"],
            max_steps=int(spec["max_steps"]),
        )

        # Re-seed for reproducibility across resets
        self._rng.seed(None)

        # Build zones and orders
        zones, delivery_zones = self._build_zones(self._state.grid_size)
        self._state.zones = zones
        self._state.delivery_zones = delivery_zones

        orders = self._materialize_orders(canonical, spec, zones, delivery_zones)
        self._order_lookup = {o.order_id: o for o in orders}
        self._pending_order_ids = deque(o.order_id for o in orders)
        self._completed_order_ids = []
        self._failed_order_ids = []

        # Generate obstacles (reachability-safe)
        self._state.obstacles = self._generate_obstacles(
            grid_size=self._state.grid_size,
            obstacle_count=int(spec["obstacle_count"]),
            orders=orders,
            delivery_zones=delivery_zones,
        )
        self._state.total_orders_expected = len(orders)

        # Reset episode counters
        self._collision_count = 0
        self._total_steps = 0
        self._priority_actions = 0
        self._priority_compliant_actions = 0
        self._episode_done = False

        # Reset robots with spread-out starting positions
        self._init_robots()
        start_positions = self._spread_start_positions(self._state.grid_size)
        for idx, (rid, robot) in enumerate(self._robots.items()):
            robot.pos = start_positions[idx]
            robot.inventory = []
            robot.steps_taken = 0
            robot.assigned_order_id = None
            robot.collisions = 0

        # Pre-assign orders so robots don't both chase the same one
        self._assign_orders_to_robots()

        return self._make_observations(message="Episode reset. Robots ready.")

    def step(
        self, actions: Dict[RobotId, int]
    ) -> Tuple[Dict[RobotId, WarehouseObservation], float, bool]:
        """Advance all robots one step simultaneously.

        Parameters
        ----------
        actions:
            Mapping of robot_id → action_id (0-5).

        Returns
        -------
        observations:
            Per-robot ``WarehouseObservation``.
        reward:
            Shared scalar reward for this step.
        done:
            ``True`` when the episode is over.
        """
        if self._episode_done:
            return self._make_observations(message="Episode already done."), 0.0, True

        self._total_steps += 1
        step_reward = 0.0
        messages: List[str] = []

        # --- 1. Compute proposed next positions for all robots ---
        proposed: Dict[RobotId, Position] = {}
        for rid, robot in self._robots.items():
            action_id = actions.get(rid, 0)
            if action_id in MOVE_DELTAS:
                dx, dy = MOVE_DELTAS[action_id]
                candidate = (robot.pos[0] + dx, robot.pos[1] + dy)
                other_positions = [
                    r.pos for r2id, r in self._robots.items() if r2id != rid
                ]
                if robot.can_move_to(
                    candidate,
                    self._state.obstacles,
                    self._state.grid_size,
                    other_positions,
                ):
                    proposed[rid] = candidate
                else:
                    proposed[rid] = robot.pos  # blocked, stay put
            else:
                proposed[rid] = robot.pos  # non-move action, position unchanged

        # --- 2. Collision resolution: if two robots target the same cell,
        #        neither moves (conservative policy) ---
        target_counts: Dict[Position, int] = {}
        for pos in proposed.values():
            target_counts[pos] = target_counts.get(pos, 0) + 1

        for rid, robot in self._robots.items():
            action_id = actions.get(rid, 0)
            if action_id in MOVE_DELTAS:
                if target_counts[proposed[rid]] > 1:
                    # Collision — penalise and keep robot in place
                    self._collision_count += 1
                    robot.collisions += 1
                    step_reward -= 0.1
                    messages.append(f"{rid}: collision averted at {proposed[rid]}.")
                    proposed[rid] = robot.pos

        # --- 3. Apply movements ---
        for rid, robot in self._robots.items():
            action_id = actions.get(rid, 0)
            if action_id in MOVE_DELTAS:
                robot.pos = proposed[rid]
                robot.steps_taken += 1

        # --- 4. Apply non-move actions (pick / deliver) ---
        for rid, robot in self._robots.items():
            action_id = actions.get(rid, 0)
            if action_id == 4:
                r, msg = self._apply_pick(robot)
                step_reward += r
                messages.append(f"{rid}: {msg}")
            elif action_id == 5:
                r, msg = self._apply_deliver(robot)
                step_reward += r
                messages.append(f"{rid}: {msg}")

        # --- 5. Re-assign orders to idle robots ---
        self._assign_orders_to_robots()

        # --- 6. Per-step efficiency penalty ---
        step_reward -= 0.001 * self.num_robots

        # --- 7. Check termination ---
        all_done = not self._pending_order_ids and all(
            r.assigned_order_id is None for r in self._robots.values()
        )
        max_steps_hit = self._total_steps >= self._state.max_steps
        self._episode_done = all_done or max_steps_hit

        if self._episode_done:
            episode_score = self._compute_episode_score()
            self._state.score = episode_score
            step_reward += episode_score
            messages.append(
                f"Episode complete. Score={episode_score:.4f} "
                f"| Completed={len(self._completed_order_ids)}/{self._state.total_orders_expected} "
                f"| Collisions={self._collision_count}"
            )

        combined_message = " ".join(m for m in messages if m).strip()
        obs = self._make_observations(message=combined_message)
        return obs, step_reward, self._episode_done

    @property
    def robots(self) -> Dict[RobotId, Robot]:
        """Read-only access to robot objects (for tests and notebooks)."""
        return self._robots

    @property
    def game_state(self) -> WarehouseGameState:
        return self._state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_robots(self) -> None:
        self._robots = {
            f"R{i + 1}": Robot(f"R{i + 1}", (0, 0))
            for i in range(self.num_robots)
        }

    def _spread_start_positions(self, grid_size: Position) -> List[Position]:
        """Return evenly spread starting positions along the bottom row."""
        gw, gh = grid_size
        step = max(1, gw // (self.num_robots + 1))
        return [(step * (i + 1), gh - 1) for i in range(self.num_robots)]

    def _normalize_task(self, task_name: str) -> str:
        return task_name if task_name in TASK_SPECS else "simple_order"

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def _assign_orders_to_robots(self) -> None:
        """Give idle robots the next pending order (round-robin style)."""
        for robot in self._robots.values():
            # Check if the robot's current order is still valid
            if robot.assigned_order_id is not None:
                order = self._order_lookup.get(robot.assigned_order_id)
                if order and order.status in {"completed", "completed_with_fallback", "failed_deadline", "failed"}:
                    robot.assigned_order_id = None

            if robot.assigned_order_id is None and self._pending_order_ids:
                next_id = self._pending_order_ids.popleft()
                robot.assigned_order_id = next_id
                order = self._order_lookup[next_id]
                order.status = "active"
                order.activated_step = self._total_steps

    def _apply_pick(self, robot: Robot) -> Tuple[float, str]:
        """Try to pick an item at the robot's current position."""
        if robot.assigned_order_id is None:
            return -0.05, "No assigned order."

        order = self._order_lookup.get(robot.assigned_order_id)
        if order is None:
            return -0.05, "Assigned order not found."

        # Find an eligible item at this position
        item = self._find_item_at(order, robot.pos)
        if item is None:
            return -0.05, f"No item to pick at {robot.pos}."

        eligible = self._eligible_names(order)
        self._priority_actions += 1
        highest = self._highest_priority_eligible(order)
        if highest and item.name == highest.name:
            self._priority_compliant_actions += 1

        reward = 0.1 * float(item.priority)
        if item.name in eligible:
            reward += 0.15
        else:
            reward -= 0.20

        item.picked = True
        robot.inventory.append(item)
        return reward, f"Picked {item.name} (priority={item.priority})."

    def _apply_deliver(self, robot: Robot) -> Tuple[float, str]:
        """Try to deliver the robot's inventory at its current position."""
        if robot.assigned_order_id is None:
            return -0.05, "No assigned order."

        order = self._order_lookup.get(robot.assigned_order_id)
        if order is None:
            return -0.05, "Assigned order not found."

        delivery_zone = self._zone_at(robot.pos)
        if delivery_zone is None:
            return -0.30, "Not in a delivery zone."
        if delivery_zone.name != order.delivery_zone:
            return -0.30, f"Wrong zone (expected {order.delivery_zone}, got {delivery_zone.name})."

        required = [i for i in order.items if i.in_stock and not i.picked]
        if required:
            names = ", ".join(i.name for i in required)
            return -0.05, f"Cannot deliver yet — missing: {names}."

        for item in order.items:
            item.delivered = True
        order.status = "completed"
        order.completion_step = self._total_steps

        self._completed_order_ids.append(order.order_id)
        self._state.completed_orders.append(order.order_id)
        robot.inventory = []
        robot.assigned_order_id = None

        # Deadline bonus
        bonus = 0.0
        if order.deadline_steps and order.activated_step is not None:
            elapsed = self._total_steps - order.activated_step
            slack = order.deadline_steps - elapsed
            if slack >= 0:
                bonus = 0.1 * (slack / max(order.deadline_steps, 1))

        reward = 0.50 + 0.30 + bonus
        return reward, f"Delivered order {order.order_id} to {delivery_zone.name}. Bonus={bonus:.3f}"

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    def _compute_episode_score(self) -> float:
        total = max(self._state.total_orders_expected, 1)
        completed = len(self._completed_order_ids)

        completion_ratio = completed / total

        # Coordination efficiency: did both robots do roughly equal work?
        work_done = [r.steps_taken for r in self._robots.values()]
        avg_work = sum(work_done) / max(len(work_done), 1)
        imbalance = sum(abs(w - avg_work) for w in work_done) / max(avg_work * len(work_done), 1)
        coordination_efficiency = max(0.0, 1.0 - imbalance)

        # Collision avoidance: penalise proportionally
        max_tolerable_collisions = max(self._total_steps * 0.1, 1)
        collision_avoidance = max(0.0, 1.0 - (self._collision_count / max_tolerable_collisions))

        priority_compliance = (
            self._priority_compliant_actions / float(self._priority_actions)
            if self._priority_actions > 0
            else 1.0
        )

        score = (
            completion_ratio * 0.50
            + coordination_efficiency * 0.25
            + collision_avoidance * 0.15
            + priority_compliance * 0.10
        )
        return clamp_score(score)

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def _make_observations(self, message: str = "") -> Dict[RobotId, WarehouseObservation]:
        all_visible = self._all_visible_items()
        obs: Dict[RobotId, WarehouseObservation] = {}
        for rid, robot in self._robots.items():
            assigned_order = (
                self._order_lookup.get(robot.assigned_order_id)
                if robot.assigned_order_id
                else None
            )
            deadline_remaining: Optional[int] = None
            if assigned_order and assigned_order.deadline_steps and assigned_order.activated_step is not None:
                elapsed = self._total_steps - assigned_order.activated_step
                deadline_remaining = assigned_order.deadline_steps - elapsed

            obs[rid] = WarehouseObservation(
                robot_pos=robot.pos,
                visible_items=[i.model_copy(deep=True) for i in all_visible],
                items_left=[i.position for i in all_visible],
                obstacles=self._state.obstacles,
                inventory=[i.model_copy(deep=True) for i in robot.inventory],
                inventory_count=len(robot.inventory),
                current_order=assigned_order.model_copy(deep=True) if assigned_order else None,
                order_queue_size=len(self._pending_order_ids),
                delivery_zones=[z.model_copy(deep=True) for z in self._state.delivery_zones],
                deadline_remaining=deadline_remaining,
                episode_history_summary=(
                    f"Step {self._total_steps}/{self._state.max_steps} | "
                    f"Completed={len(self._completed_order_ids)}/{self._state.total_orders_expected} | "
                    f"Collisions={self._collision_count}"
                ),
                message=message,
                render=self._render(highlight_robot=rid),
            )
        return obs

    def _render(self, highlight_robot: Optional[str] = None) -> str:
        """ASCII grid with all robot positions marked."""
        gw, gh = self._state.grid_size
        grid = [["." for _ in range(gw)] for _ in range(gh)]

        for zone in self._state.delivery_zones:
            for x in range(zone.top_left[0], zone.bottom_right[0] + 1):
                for y in range(zone.top_left[1], zone.bottom_right[1] + 1):
                    if 0 <= x < gw and 0 <= y < gh:
                        grid[y][x] = "S"

        for ox, oy in self._state.obstacles:
            if 0 <= ox < gw and 0 <= oy < gh:
                grid[oy][ox] = "#"

        for item in self._all_visible_items():
            x, y = item.position
            if 0 <= x < gw and 0 <= y < gh:
                grid[y][x] = "$"

        for rid, robot in self._robots.items():
            x, y = robot.pos
            if 0 <= x < gw and 0 <= y < gh:
                label = rid[1] if highlight_robot != rid else "*"
                grid[y][x] = label

        lines = ["+ " + "- " * gw + "+"]
        for row in grid:
            lines.append("| " + " ".join(row) + " |")
        lines.append("+ " + "- " * gw + "+")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Zone / grid helpers (mirrors WarehouseEnvironment private methods)
    # ------------------------------------------------------------------

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
            Zone(name="STAGE_1", top_left=(0, height - 1), bottom_right=(min(1, width - 1), height - 1), zone_type="delivery"),
            Zone(name="STAGE_2", top_left=(max(width - 2, 0), height - 1), bottom_right=(width - 1, height - 1), zone_type="delivery"),
        ]
        return zones, delivery_zones

    def _materialize_orders(
        self,
        task_name: str,
        spec: dict,
        zones: List[Zone],
        delivery_zones: List[Zone],
    ) -> List[Order]:
        used: Set[Position] = {(0, 0)}
        zone_map = {z.name: z for z in zones}
        dzone_map = {z.name: z for z in delivery_zones}
        orders: List[Order] = []

        for idx, ospec in enumerate(spec["orders"]):
            items: List[OrderItem] = []
            for ispec in ospec["items"]:
                zone = zone_map[ispec["zone"]]
                in_stock = not (
                    ispec.get("can_be_out_of_stock")
                    and self._rng.random() < ispec.get("out_of_stock_probability", 0.0)
                )
                if in_stock:
                    pos = self._sample_pos(zone, used)
                    used.add(pos)
                else:
                    pos = (-1, -1)
                items.append(OrderItem(
                    name=ispec["name"],
                    position=pos,
                    zone=ispec["zone"],
                    is_fragile=bool(ispec.get("is_fragile", False)),
                    priority=int(ispec.get("priority", 3)),
                    in_stock=in_stock,
                ))

            dzone = dzone_map[ospec["delivery_zone"]]
            deps = [
                OrderDependency(before_item=b, after_item=a)
                for b, a in ospec.get("dependencies", [])
            ]
            orders.append(Order(
                order_id=f"mr-{task_name}-{idx + 1}",
                instruction_text=f"Fulfill order {idx + 1}: pick {', '.join(i.name for i in items)} and deliver to {dzone.name}.",
                items=items,
                delivery_zone=dzone.name,
                delivery_position=dzone.anchor,
                dependencies=deps,
                deadline_steps=ospec.get("deadline_steps"),
                status="pending",
            ))

        return orders

    def _generate_obstacles(
        self,
        *,
        grid_size: Position,
        obstacle_count: int,
        orders: List[Order],
        delivery_zones: List[Zone],
    ) -> List[Position]:
        reserved: Set[Position] = {(0, 0)}
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
        for _ in range(50):
            sample = self._rng.sample(candidates, k=min(obstacle_count, len(candidates)))
            target_pts = [o.delivery_position for o in orders] + [
                i.position for o in orders for i in o.items if i.in_stock
            ]
            if all(self._path_exists((0, 0), p, grid_size, sample) for p in target_pts):
                return sorted(sample)
        return sorted(candidates[:min(obstacle_count, len(candidates))])

    def _path_exists(
        self,
        start: Position,
        goal: Position,
        grid_size: Position,
        obstacles: List[Position],
    ) -> bool:
        """BFS reachability check (mirrors WarehouseEnvironment._path_exists)."""
        if start == goal:
            return True
        blocked: Set[Position] = set(obstacles)
        gw, gh = grid_size
        visited: Set[Position] = {start}
        queue: deque[Position] = deque([start])
        while queue:
            cx, cy = queue.popleft()
            for dx, dy in MOVE_DELTAS.values():
                nx, ny = cx + dx, cy + dy
                nb = (nx, ny)
                if nb == goal:
                    return True
                if 0 <= nx < gw and 0 <= ny < gh and nb not in blocked and nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        return False

    def _sample_pos(self, zone: Zone, used: Set[Position]) -> Position:
        candidates = [
            (x, y)
            for x in range(zone.top_left[0], zone.bottom_right[0] + 1)
            for y in range(zone.top_left[1], zone.bottom_right[1] + 1)
            if (x, y) not in used
        ]
        return self._rng.choice(candidates) if candidates else zone.anchor

    def _zone_at(self, pos: Position) -> Optional[Zone]:
        for zone in self._state.delivery_zones:
            if zone.contains(pos):
                return zone
        return None

    def _all_visible_items(self) -> List[OrderItem]:
        visible: List[OrderItem] = []
        for order in self._order_lookup.values():
            for item in order.items:
                if item.in_stock and not item.picked and not item.delivered:
                    visible.append(item.model_copy(deep=True))
        return visible

    def _find_item_at(self, order: Order, pos: Position) -> Optional[OrderItem]:
        for item in order.items:
            if item.position == pos and item.in_stock and not item.picked and not item.delivered:
                return item
        return None

    def _eligible_names(self, order: Order) -> Set[str]:
        picked = {i.name for i in order.items if i.picked}
        eligible: Set[str] = set()
        for item in order.items:
            if item.picked or not item.in_stock:
                continue
            prereqs = {d.before_item for d in order.dependencies if d.after_item == item.name}
            if prereqs.issubset(picked):
                eligible.add(item.name)
        return eligible

    def _highest_priority_eligible(self, order: Order) -> Optional[OrderItem]:
        names = self._eligible_names(order)
        candidates = [i for i in order.items if i.name in names and i.in_stock and not i.picked]
        if not candidates:
            return None
        return max(candidates, key=lambda i: i.priority)
