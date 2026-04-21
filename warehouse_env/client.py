from __future__ import annotations

from typing import Any, Dict, List

from openenv.core.client_types import StepResult
from openenv.core.env_client import EnvClient

from .models import (
    Order,
    OrderDependency,
    OrderItem,
    ParsedPlan,
    PlanStep,
    WarehouseAction,
    WarehouseGameState,
    WarehouseObservation,
    Zone,
)


def _parse_zone(payload: Dict[str, Any]) -> Zone:
    return Zone(
        name=payload.get("name", ""),
        top_left=tuple(payload.get("top_left", [0, 0])),
        bottom_right=tuple(payload.get("bottom_right", [0, 0])),
        zone_type=payload.get("zone_type", "storage"),
    )


def _parse_item(payload: Dict[str, Any]) -> OrderItem:
    return OrderItem(
        name=payload.get("name", ""),
        position=tuple(payload.get("position", [0, 0])),
        zone=payload.get("zone", ""),
        is_fragile=bool(payload.get("is_fragile", False)),
        priority=int(payload.get("priority", 3)),
        in_stock=bool(payload.get("in_stock", True)),
        picked=bool(payload.get("picked", False)),
        delivered=bool(payload.get("delivered", False)),
    )


def _parse_order(payload: Dict[str, Any]) -> Order:
    return Order(
        order_id=payload.get("order_id", ""),
        instruction_text=payload.get("instruction_text", ""),
        items=[_parse_item(item) for item in payload.get("items", [])],
        delivery_zone=payload.get("delivery_zone", ""),
        delivery_position=tuple(payload.get("delivery_position", [0, 0])),
        dependencies=[
            OrderDependency(
                before_item=dependency.get("before_item", ""),
                after_item=dependency.get("after_item", ""),
            )
            for dependency in payload.get("dependencies", [])
        ],
        deadline_steps=payload.get("deadline_steps"),
        status=payload.get("status", "pending"),
        activated_step=payload.get("activated_step"),
        completion_step=payload.get("completion_step"),
        notes=list(payload.get("notes", [])),
    )


def _parse_plan(payload: Dict[str, Any]) -> ParsedPlan:
    return ParsedPlan(
        ordered_item_names=list(payload.get("ordered_item_names", [])),
        steps=[
            PlanStep(
                action=step.get("action", ""),
                target=step.get("target", ""),
                zone=step.get("zone"),
                notes=step.get("notes", ""),
            )
            for step in payload.get("steps", [])
        ],
        delivery_zone_name=payload.get("delivery_zone_name"),
        priorities=list(payload.get("priorities", [])),
        ambiguity_notes=list(payload.get("ambiguity_notes", [])),
        raw_response=payload.get("raw_response"),
    )


class WarehouseEnv(EnvClient[WarehouseAction, WarehouseObservation, WarehouseGameState]):
    def _step_payload(self, action: WarehouseAction) -> dict:
        payload = {"action_id": action.action_id}
        if action.plan_response:
            payload["plan_response"] = action.plan_response
        return payload

    def _parse_result(self, payload: dict) -> StepResult:
        observation_payload = payload.get("observation", {})
        observation = WarehouseObservation(
            done=payload.get("done", False),
            reward=payload.get("reward"),
            robot_pos=tuple(observation_payload.get("robot_pos", [0, 0])),
            visible_items=[_parse_item(item) for item in observation_payload.get("visible_items", [])],
            items_left=[tuple(item) for item in observation_payload.get("items_left", [])],
            obstacles=[tuple(position) for position in observation_payload.get("obstacles", [])],
            inventory=[_parse_item(item) for item in observation_payload.get("inventory", [])],
            inventory_count=int(observation_payload.get("inventory_count", 0)),
            current_order=_parse_order(observation_payload["current_order"])
            if observation_payload.get("current_order")
            else None,
            order_queue_size=int(observation_payload.get("order_queue_size", 0)),
            delivery_zones=[_parse_zone(zone) for zone in observation_payload.get("delivery_zones", [])],
            deadline_remaining=observation_payload.get("deadline_remaining"),
            episode_history_summary=observation_payload.get("episode_history_summary", ""),
            message=observation_payload.get("message", ""),
            render=observation_payload.get("render", ""),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: dict) -> WarehouseGameState:
        return WarehouseGameState(
            episode_id=payload.get("episode_id"),
            task_name=payload.get("task_name", "simple_order"),
            step_count=int(payload.get("step_count", 0)),
            grid_size=tuple(payload.get("grid_size", [10, 10])),
            robot_pos=tuple(payload.get("robot_pos", [0, 0])),
            items=[_parse_item(item) for item in payload.get("items", [])],
            obstacles=[tuple(position) for position in payload.get("obstacles", [])],
            inventory=[_parse_item(item) for item in payload.get("inventory", [])],
            max_steps=int(payload.get("max_steps", 100)),
            zones=[_parse_zone(zone) for zone in payload.get("zones", [])],
            delivery_zones=[_parse_zone(zone) for zone in payload.get("delivery_zones", [])],
            orders=[_parse_order(order) for order in payload.get("orders", [])],
            active_order_id=payload.get("active_order_id"),
            completed_orders=list(payload.get("completed_orders", [])),
            failed_orders=list(payload.get("failed_orders", [])),
            current_plan=_parse_plan(payload["current_plan"]) if payload.get("current_plan") else None,
            score=float(payload.get("score", 0.0001)),
            total_reward=float(payload.get("total_reward", 0.0)),
            priority_actions=int(payload.get("priority_actions", 0)),
            priority_compliant_actions=int(payload.get("priority_compliant_actions", 0)),
            dependency_violations=int(payload.get("dependency_violations", 0)),
            deadlines_met=int(payload.get("deadlines_met", 0)),
            total_orders_expected=int(payload.get("total_orders_expected", 0)),
        )
