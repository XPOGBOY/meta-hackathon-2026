"""Bounded reward and episode-score functions for the warehouse environment.

This module is intentionally pure (no I/O, no global state) so that the same
math runs identically inside the live environment, the offline evaluator, and
the unit tests.

Two distinct signals are emitted:

* ``compute_reward`` — a *per-step* shaped reward. Encourages the agent to
  pick the right items in the right order, deliver to the correct staging
  zone, respect deadlines, and avoid invalid actions.
* ``compute_episode_score`` — a *per-episode* clamped scalar in
  ``[MIN_SCORE, MAX_SCORE]``. This is the headline number reported to judges
  and to the self-improvement loop. It is a weighted blend of completion,
  priority compliance, efficiency, and improvement-over-baseline.

The hard bounds ``MIN_SCORE = 0.0001`` and ``MAX_SCORE = 0.9999`` are part of
the public contract: downstream consumers (curriculum controller, OpenEnv
leaderboard) assume the score never collapses to exactly 0 or saturates at 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from warehouse_env.models import OrderItem, WarehouseGameState

# Hard bounds for the per-episode score. These are part of the public API
# contract — downstream curricula and dashboards rely on a strictly open
# interval so that "no progress" and "perfect" stay distinguishable from
# numeric edge cases.
MIN_SCORE: float = 0.0001
MAX_SCORE: float = 0.9999


@dataclass
class RewardContext:
    """Per-step accumulator describing what just happened in the environment.

    The environment fills this struct as it processes a single ``step()``
    call, then passes it to :func:`compute_reward`. Keeping the *event flags*
    separated from the *reward arithmetic* makes the reward function trivial
    to unit-test and to reason about during a code review.

    Attributes:
        picked_item: The ``OrderItem`` actually picked this step, if any.
            Used to award a priority-weighted bonus.
        picked_in_correct_order: ``True`` when the picked item satisfied all
            of its dependency prerequisites.
        picked_out_of_order: ``True`` when the picked item violated a
            ``before -> after`` dependency edge.
        fragile_risk: ``True`` when the agent picked a fragile item while
            non-fragile items in the same order were still on the floor
            (those should usually be picked first to cushion the fragile one).
        delivered_to_correct_zone: ``True`` when the deliver action landed in
            the order's expected staging zone.
        delivered_to_wrong_zone: ``True`` when deliver was used outside any
            staging zone or in the wrong staging zone.
        order_fully_completed: ``True`` on the step that closes out an order.
        completed_before_deadline: ``True`` when the order finished with
            steps to spare relative to its deadline.
        deadline_exceeded: ``True`` when an active order ran out of time.
        remaining_steps: Steps left on the order's deadline at delivery time.
        total_deadline: Original deadline budget for the active order. Used
            as the denominator of the on-time bonus.
        invalid_action: ``True`` for any action the env could not execute
            (e.g. pick on an empty cell, deliver with missing items).
        obstacle_collision: ``True`` if a movement action was blocked by an
            obstacle.
        out_of_stock_encountered: ``True`` if the agent tried to interact
            with an item that was sampled as out-of-stock this episode.
    """

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
    """Clamp a raw episode score into the public ``[MIN_SCORE, MAX_SCORE]`` range.

    Args:
        score: The unclamped score produced by :func:`compute_episode_score`
            or any external evaluator.

    Returns:
        A float guaranteed to lie in ``[MIN_SCORE, MAX_SCORE]``. Values below
        the floor are lifted to ``MIN_SCORE``; values above the ceiling are
        capped at ``MAX_SCORE``.
    """
    return min(MAX_SCORE, max(MIN_SCORE, score))


def compute_reward(
    state: WarehouseGameState,
    action_id: int,
    result: RewardContext,
) -> float:
    """Compute the dense per-step reward emitted by ``WarehouseEnvironment.step``.

    The shaping is intentionally simple and additive — every term is either
    a constant or a small linear function of the context. This keeps the
    signal interpretable for both the DQN trainer and human reviewers.

    Args:
        state: The current game state. Reserved for future curriculum-aware
            shaping; unused today but kept in the signature so downstream
            extensions don't break callers.
        action_id: The integer action that was executed (0-3 = move,
            4 = pick, 5 = deliver). Currently unused but preserved for the
            same reason as ``state``.
        result: The :class:`RewardContext` populated by the environment for
            this step.

    Returns:
        A dense scalar reward. May be negative (penalty) or positive
        (progress). The terminal call in ``step()`` adds the clamped episode
        score on top of this, so episode totals stay well-bounded.
    """
    reward = 0.0

    # Picking *anything* legitimately is rewarded proportional to its
    # business priority — high-value items are worth ~5x a bottom-tier item.
    if result.picked_item is not None:
        reward += 0.1 * float(result.picked_item.priority)

    # Dependency-respecting picks get a flat bonus; violations are punished
    # twice as hard, so the agent learns the topological order quickly.
    if result.picked_in_correct_order:
        reward += 0.15
    elif result.picked_out_of_order:
        reward -= 0.2

    # Picking a fragile item while non-fragile items are still on the floor
    # is a soft penalty: it's not "wrong", but it's risky packing.
    if result.fragile_risk:
        reward -= 0.05

    # Delivery shaping: the symmetric +/- 0.3 keeps the reward-magnitude of
    # a correct delivery comparable to the cost of a wrong-zone mistake.
    if result.delivered_to_correct_zone:
        reward += 0.3
    elif result.delivered_to_wrong_zone:
        reward -= 0.3

    # Big terminal bonus for closing out an entire order. Deliberately the
    # largest single positive term so completion dominates exploration.
    if result.order_fully_completed:
        reward += 0.5

    # On-time bonus is fractional in the deadline — finishing with more
    # slack pays more, but the term is bounded above by 0.1.
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

    # Tiny per-step time tax. Encourages efficient routing without
    # discouraging the exploration the DQN needs in early training.
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
    """Aggregate end-of-episode metrics into a single bounded headline score.

    The score is a convex combination of four interpretable axes:

    ============================  ======  ======================================
    Component                     Weight  Meaning
    ============================  ======  ======================================
    Completion ratio              0.50    Fraction of orders fully delivered.
    Priority compliance           0.20    Fraction of picks that targeted the
                                          highest-priority eligible item.
    Efficiency ratio              0.15    Steps left over vs. ``max_steps``.
    Improvement-over-baseline     0.15    Self-improvement signal — how much
                                          the recent rolling average beats the
                                          historical baseline.
    ============================  ======  ======================================

    Weights sum to 1.0, so any individual component caps the contribution it
    can make. The final result is clamped to ``[MIN_SCORE, MAX_SCORE]``.

    Args:
        total_orders: Number of orders the episode was supposed to fulfill.
            Returns ``MIN_SCORE`` immediately if non-positive.
        completed_orders: Number of orders actually delivered.
        priority_actions: Total number of pick actions that had at least one
            "right answer" available (i.e. there *was* a highest-priority
            eligible item at the time of the pick).
        priority_compliant_actions: Of those, how many actually picked it.
        steps_taken: Steps used in the episode.
        max_steps: Step budget for the episode.
        baseline_score: Rolling baseline (typically the mean of the first
            few episodes for this agent), used to compute self-improvement.
        current_average_score: Rolling recent-episodes average, used as the
            "now" half of the improvement delta.

    Returns:
        A float in ``[MIN_SCORE, MAX_SCORE]``.
    """
    if total_orders <= 0:
        return MIN_SCORE

    completion_ratio = completed_orders / float(total_orders)
    priority_compliance = (
        priority_compliant_actions / float(priority_actions)
        if priority_actions > 0
        else 1.0
    )
    efficiency_ratio = max(0.0, 1.0 - (steps_taken / float(max(max_steps, 1))))

    # Improvement axis: when there is no baseline yet, fall back to the raw
    # recent average so early episodes still produce a meaningful gradient.
    # Otherwise, normalise the lift against the baseline and clamp to [0, 1]
    # so a single great episode can't dominate the headline number.
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
