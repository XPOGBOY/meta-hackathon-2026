from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from warehouse_env.models import OrderItem, WarehouseGameState

MIN_SCORE = 0.0001
MAX_SCORE = 0.9999


@dataclass
class RewardContext:
    picked_item: Optional[OrderItem] = None
    picked_in_correct_order: bool = False
    picked_out_of_order: bool = False
    fragile_risk: bool = False
    delivered_to_correct_zone: bool = False
    delivered_to_wrong_zone: bool = False
    order_fully_completed: bool = False
    completed_before_deadline: bool = False
    deadline_exceeded: bool = False
    remaining_steps: int = 0
    total_deadline: int = 1
    invalid_action: bool = False
    obstacle_collision: bool = False
    out_of_stock_encountered: bool = False


def clamp_score(score: float) -> float:
    return min(MAX_SCORE, max(MIN_SCORE, score))


def compute_reward(
    state: WarehouseGameState,
    action_id: int,
    result: RewardContext,
) -> float:
    reward = 0.0

    if result.picked_item is not None:
        reward += 0.1 * float(result.picked_item.priority)

    if result.picked_in_correct_order:
        reward += 0.15
    elif result.picked_out_of_order:
        reward -= 0.2

    if result.fragile_risk:
        reward -= 0.05

    if result.delivered_to_correct_zone:
        reward += 0.3
    elif result.delivered_to_wrong_zone:
        reward -= 0.3

    if result.order_fully_completed:
        reward += 0.5

    if result.completed_before_deadline and result.total_deadline > 0:
        reward += 0.1 * (result.remaining_steps / float(result.total_deadline))
    elif result.deadline_exceeded:
        reward -= 0.2

    if result.invalid_action:
        reward -= 0.05

    if result.obstacle_collision:
        reward -= 0.05

    if result.out_of_stock_encountered:
        reward -= 0.03

    # Encourage efficient execution while still allowing exploration.
    reward -= 0.001

    return reward


def compute_episode_score(
    *,
    total_orders: int,
    completed_orders: int,
    priority_actions: int,
    priority_compliant_actions: int,
    steps_taken: int,
    max_steps: int,
    baseline_score: float,
    current_average_score: float,
) -> float:
    if total_orders <= 0:
        return MIN_SCORE

    completion_ratio = completed_orders / float(total_orders)
    priority_compliance = (
        priority_compliant_actions / float(priority_actions)
        if priority_actions > 0
        else 1.0
    )
    efficiency_ratio = max(0.0, 1.0 - (steps_taken / float(max(max_steps, 1))))

    if baseline_score <= 0:
        improvement = current_average_score
    else:
        improvement = max(
            0.0,
            min(1.0, (current_average_score - baseline_score) / max(baseline_score, 0.1)),
        )

    final_score = (
        completion_ratio * 0.5
        + priority_compliance * 0.2
        + efficiency_ratio * 0.15
        + improvement * 0.15
    )
    return clamp_score(final_score)
