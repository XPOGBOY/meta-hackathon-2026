from __future__ import annotations

import os
import sys
from collections import deque
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from warehouse_env.client import WarehouseEnv
from warehouse_env.instruction_parser import InstructionParser
from warehouse_env.models import Order, OrderItem, ParsedPlan, WarehouseAction
from warehouse_env.reward import MAX_SCORE, MIN_SCORE, clamp_score
from warehouse_env.self_improve import EpisodeRecord, PerformanceTracker, StrategyAdapter

Position = Tuple[int, int]

MOVE_DELTAS: Dict[int, Position] = {
    0: (0, -1),
    1: (0, 1),
    2: (-1, 0),
    3: (1, 0),
}

DEFAULT_TASKS = [
    "simple_order",
    "multi_step_order",
    "order_queue",
    "adaptive_fulfillment",
]
DEFAULT_PORT_CANDIDATES = [7860, 8000, 8001, 8002]


def log_diagnostic(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit_start(task_id: str) -> None:
    print(f"[START] task={task_id}", flush=True)


def emit_step(task_id: str, step_count: int, reward: float) -> None:
    print(f"[STEP] task={task_id} step={step_count} reward={reward:.4f}", flush=True)


def emit_end(task_id: str, score: float) -> None:
    print(f"[END] task={task_id} score={clamp_score(score):.4f}", flush=True)


def _normalize_base_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://", "ws://", "wss://")):
        url = f"http://{url}"
    if url.endswith("/ws"):
        url = url[:-3]
    return url.rstrip("/")


def _candidate_base_urls() -> List[str]:
    candidates: List[str] = []
    seen = set()

    for key in ("OPENENV_BASE_URL", "OPENENV_URL", "BASE_URL", "SERVER_URL"):
        value = os.getenv(key, "").strip()
        if value:
            normalized = _normalize_base_url(value)
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)

    for key in ("OPENENV_PORT", "PORT"):
        value = os.getenv(key, "").strip()
        if value.isdigit():
            for host in ("127.0.0.1", "localhost"):
                url = f"http://{host}:{int(value)}"
                if url not in seen:
                    seen.add(url)
                    candidates.append(url)

    for port in DEFAULT_PORT_CANDIDATES:
        for host in ("127.0.0.1", "localhost"):
            url = f"http://{host}:{port}"
            if url not in seen:
                seen.add(url)
                candidates.append(url)

    return candidates


def resolve_env_url(tasks: Sequence[str]) -> Optional[str]:
    probe_task = tasks[0] if tasks else "simple_order"
    for candidate in _candidate_base_urls():
        try:
            client = WarehouseEnv(base_url=candidate, connect_timeout_s=2.0).sync()
            with client:
                client.reset(task_name=probe_task)
            log_diagnostic(f"[INFO] Connected to environment at {candidate}")
            return candidate
        except Exception as exc:
            log_diagnostic(f"[WARN] Could not reach {candidate}: {exc}")
    return None


def _neighbors(
    pos: Position,
    grid_size: Position,
    obstacles: Iterable[Position],
) -> Iterable[Tuple[Position, int]]:
    blocked = set(obstacles)
    width, height = grid_size
    for action_id, (dx, dy) in MOVE_DELTAS.items():
        nxt = (pos[0] + dx, pos[1] + dy)
        if 0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in blocked:
            yield nxt, action_id


def shortest_path(
    start: Position,
    goal: Position,
    grid_size: Position,
    obstacles: Sequence[Position],
) -> Optional[List[int]]:
    if start == goal:
        return []

    queue = deque([start])
    parents: Dict[Position, Tuple[Optional[Position], Optional[int]]] = {start: (None, None)}

    while queue:
        current = queue.popleft()
        for nxt, action_id in _neighbors(current, grid_size, obstacles):
            if nxt in parents:
                continue
            parents[nxt] = (current, action_id)
            if nxt == goal:
                path: List[int] = []
                cursor = goal
                while True:
                    prev, move = parents[cursor]
                    if prev is None or move is None:
                        break
                    path.append(move)
                    cursor = prev
                path.reverse()
                return path
            queue.append(nxt)

    return None


def _dependency_ready(item: OrderItem, order: Order, picked_names: set[str]) -> bool:
    prerequisites = {
        dependency.before_item
        for dependency in order.dependencies
        if dependency.after_item == item.name
    }
    return prerequisites.issubset(picked_names)


def _tsp_order(
    start: Position,
    items: Sequence[OrderItem],
    grid_size: Position,
    obstacles: Sequence[Position],
    plan_order: Dict[str, int],
) -> List[OrderItem]:
    if not items:
        return []
    if len(items) == 1:
        return [items[0]]

    points = [start] + [item.position for item in items]
    pair_costs: Dict[Tuple[int, int], int] = {}
    for i, src in enumerate(points):
        for j, dst in enumerate(points):
            if i == j:
                pair_costs[(i, j)] = 0
                continue
            path = shortest_path(src, dst, grid_size, obstacles)
            if path is None:
                pair_costs[(i, j)] = 10_000
            else:
                pair_costs[(i, j)] = len(path)

    item_count = len(items)
    full_mask = (1 << item_count) - 1
    dp: Dict[Tuple[int, int], Tuple[float, Optional[Tuple[int, int]]]] = {}
    for item_idx in range(item_count):
        preference_penalty = plan_order.get(items[item_idx].name, item_idx) * 0.5
        dp[(1 << item_idx, item_idx)] = (
            pair_costs[(0, item_idx + 1)] + preference_penalty,
            None,
        )

    for mask in range(1, full_mask + 1):
        for last in range(item_count):
            state = (mask, last)
            if state not in dp:
                continue
            current_cost, _ = dp[state]
            for nxt in range(item_count):
                if mask & (1 << nxt):
                    continue
                next_mask = mask | (1 << nxt)
                preference_penalty = plan_order.get(items[nxt].name, nxt) * 0.5
                next_cost = current_cost + pair_costs[(last + 1, nxt + 1)] + preference_penalty
                next_state = (next_mask, nxt)
                if next_state not in dp or next_cost < dp[next_state][0]:
                    dp[next_state] = (next_cost, state)

    best_last = min(range(item_count), key=lambda idx: dp[(full_mask, idx)][0])
    order_indices: List[int] = []
    state: Optional[Tuple[int, int]] = (full_mask, best_last)
    while state is not None:
        _, last = state
        order_indices.append(last)
        state = dp[state][1]
    order_indices.reverse()
    return [items[index] for index in order_indices]


def build_item_sequence(
    order: Order,
    plan: ParsedPlan,
    start: Position,
    grid_size: Position,
    obstacles: Sequence[Position],
) -> List[OrderItem]:
    remaining = [
        item for item in order.items if item.in_stock and not item.picked and not item.delivered
    ]
    if not remaining:
        return []

    plan_rank = {name: index for index, name in enumerate(plan.ordered_item_names)}
    picked_names = {item.name for item in order.items if item.picked}
    current_pos = start
    sequence: List[OrderItem] = []

    while remaining:
        eligible = [item for item in remaining if _dependency_ready(item, order, picked_names)]
        candidates = eligible or remaining
        ordered_candidates = _tsp_order(current_pos, candidates, grid_size, obstacles, plan_rank)
        next_item = ordered_candidates[0]
        sequence.append(next_item)
        picked_names.add(next_item.name)
        current_pos = next_item.position
        remaining = [item for item in remaining if item.name != next_item.name]

    return sequence


def build_execution_actions(
    start: Position,
    item_sequence: Sequence[OrderItem],
    delivery_position: Position,
    grid_size: Position,
    obstacles: Sequence[Position],
) -> List[int]:
    actions: List[int] = []
    current_pos = start

    for item in item_sequence:
        path = shortest_path(current_pos, item.position, grid_size, obstacles)
        if path is None:
            raise RuntimeError(f"No path to item {item.name} at {item.position}")
        actions.extend(path)
        actions.append(4)
        current_pos = item.position

    delivery_path = shortest_path(current_pos, delivery_position, grid_size, obstacles)
    if delivery_path is None:
        raise RuntimeError(f"No path to delivery zone at {delivery_position}")
    actions.extend(delivery_path)
    actions.append(5)
    return actions


def execute_task(
    env: WarehouseEnv,
    task_id: str,
    parser: InstructionParser,
    strategy_adapter: StrategyAdapter,
    tracker: PerformanceTracker,
) -> float:
    result = env.reset(task_name=task_id)
    observation = result.observation
    state = env.state()
    steps = 0

    while True:
        current_order = observation.current_order
        if current_order is None:
            if result.done:
                break
            result = env.step(WarehouseAction(action_id=3))
            observation = result.observation
            state = env.state()
            steps += 1
            emit_step(task_id, steps, float(result.reward or 0.0))
            continue

        heuristic_plan = parser.heuristic_parse(current_order)
        strategy_hint = strategy_adapter.suggest(tracker, count=3)
        if task_id in {"order_queue", "adaptive_fulfillment"}:
            queued_orders = [
                order
                for order in state.orders
                if order.status in {"pending", "active"} and order.order_id != current_order.order_id
            ]
            if queued_orders:
                ranked_orders = parser.rank_orders(
                    [current_order, *queued_orders],
                    episode_history_summary=observation.episode_history_summary,
                    strategy_hint=strategy_hint,
                )
                log_diagnostic(f"[QUEUE-PLAN] {task_id}: {ranked_orders}")

        parsed_plan = parser.parse(
            current_order,
            episode_history_summary=observation.episode_history_summary,
            strategy_hint=strategy_hint,
        )
        log_diagnostic(f"[LLM-HINT] Strategy: {strategy_hint}")
        log_diagnostic(f"[HEURISTIC-PLAN] Order {current_order.order_id}: {heuristic_plan.ordered_item_names}")
        log_diagnostic(f"[LLM-PLAN] Order {current_order.order_id}: {parsed_plan.ordered_item_names}")
        if parsed_plan.ambiguity_notes:
            log_diagnostic(f"[LLM-NOTES] Order {current_order.order_id}: {' | '.join(parsed_plan.ambiguity_notes)}")

        try:
            item_sequence = build_item_sequence(
                current_order,
                parsed_plan,
                observation.robot_pos,
                state.grid_size,
                observation.obstacles,
            )
            actions = build_execution_actions(
                observation.robot_pos,
                item_sequence,
                current_order.delivery_position,
                state.grid_size,
                observation.obstacles,
            )
        except Exception as exc:
            log_diagnostic(f"[WARN] Planner fallback for {task_id}: {exc}")
            actions = [5]

        first_action = True
        active_order_id = current_order.order_id
        for action_id in actions:
            action = WarehouseAction(action_id=action_id)
            if first_action:
                action.plan_response = parsed_plan.model_dump_json()
                first_action = False
            result = env.step(action)
            observation = result.observation
            state = env.state()
            steps += 1
            emit_step(task_id, steps, float(result.reward or 0.0))

            if result.done:
                return clamp_score(state.score)
            if observation.current_order is None or observation.current_order.order_id != active_order_id:
                break

    state = env.state()
    return clamp_score(state.score if state.score else MIN_SCORE)


def run_inference() -> None:
    env_url = resolve_env_url(DEFAULT_TASKS)
    if not env_url:
        for task_id in DEFAULT_TASKS:
            emit_start(task_id)
            emit_step(task_id, 1, MIN_SCORE)
            emit_end(task_id, MIN_SCORE)
        return

    parser = InstructionParser.from_env()
    strategy_adapter = StrategyAdapter.from_env()
    tracker = PerformanceTracker(max_episodes=30)

    try:
        client = WarehouseEnv(base_url=env_url, connect_timeout_s=5.0).sync()
        with client:
            for task_id in DEFAULT_TASKS:
                emit_start(task_id)
                final_score = MIN_SCORE
                final_score = execute_task(client, task_id, parser, strategy_adapter, tracker)
                state = client.state()
                priority_compliance = (
                    state.priority_compliant_actions / float(state.priority_actions)
                    if state.priority_actions > 0
                    else 1.0
                )
                efficiency_ratio = max(
                    0.0,
                    1.0 - (state.step_count / float(max(state.max_steps, 1))),
                )
                failure_reasons: List[str] = []
                if state.failed_orders:
                    failure_reasons.append("deadline_missed")
                if state.dependency_violations:
                    failure_reasons.append("dependency_violation")
                tracker.record_episode(
                    EpisodeRecord(
                        task_name=task_id,
                        score=state.score,
                        steps_taken=state.step_count,
                        orders_completed=len(state.completed_orders),
                        total_orders=state.total_orders_expected,
                        failure_reasons=failure_reasons,
                        priority_compliance=priority_compliance,
                        efficiency_ratio=efficiency_ratio,
                    )
                )
                emit_end(task_id, final_score if MIN_SCORE <= final_score <= MAX_SCORE else clamp_score(final_score))
    except Exception as exc:
        log_diagnostic(f"[ERROR] Inference session failed: {exc}")
        for task_id in DEFAULT_TASKS:
            emit_start(task_id)
            emit_step(task_id, 1, MIN_SCORE)
            emit_end(task_id, MIN_SCORE)
        return

    log_diagnostic("[SELF-IMPROVE SUMMARY]")
    log_diagnostic(f"  Scores: {[record.score for record in tracker.memory.list()]}")
    log_diagnostic(
        f"  Avg improvement: {tracker.recent_average_score(count=10) - tracker.baseline_score():.4f}"
    )
    log_diagnostic(f"  {tracker.summary(count=10)}")
    log_diagnostic("=" * 60)
    log_diagnostic("PERFORMANCE SUMMARY")
    log_diagnostic("=" * 60)
    for record in tracker.memory.list():
        log_diagnostic(
            f"  {record.task_name:<25} | score={record.score:.4f} | "
            f"orders={record.orders_completed}/{record.total_orders} | "
            f"steps={record.steps_taken} | priority={record.priority_compliance:.2f}"
        )
    log_diagnostic(f"  Average Score: {tracker.recent_average_score(count=10):.4f}")
    log_diagnostic(f"  Completion Rate: {tracker.completion_rate(count=10):.2f}")
    log_diagnostic(tracker.summary(count=10))
    log_diagnostic("=" * 60)


if __name__ == "__main__":
    run_inference()
