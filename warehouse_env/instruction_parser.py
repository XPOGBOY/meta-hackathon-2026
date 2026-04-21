from __future__ import annotations

import json
import os
from graphlib import TopologicalSorter
from typing import Dict, List, Optional, Sequence

from openai import OpenAI

from warehouse_env.models import Order, OrderItem, ParsedPlan, PlanStep


class InstructionParser:
    def __init__(self, client: Optional[OpenAI] = None, model_name: Optional[str] = None):
        self._client = client
        self._model_name = model_name

    @classmethod
    def from_env(cls) -> "InstructionParser":
        base_url = os.getenv("API_BASE_URL", "https://api.openai.com/v1").strip()
        api_key = (os.getenv("HF_TOKEN") or os.getenv("API_KEY") or "").strip()
        if not api_key:
            return cls()

        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            models = list(client.models.list())
            requested = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()
            model_name = requested if any(model.id == requested for model in models) else models[0].id
            return cls(client=client, model_name=model_name)
        except Exception:
            return cls()

    def parse(
        self,
        order: Order,
        episode_history_summary: str = "",
        strategy_hint: str = "",
    ) -> ParsedPlan:
        fallback_plan = self._heuristic_parse(order)
        if not self._client or not self._model_name:
            return fallback_plan

        try:
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Parse warehouse order instructions into structured JSON. "
                            "Return keys: ordered_item_names, delivery_zone_name, priorities, "
                            "ambiguity_notes, steps. Each step must have action,target,zone,notes."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Instruction: {order.instruction_text}\n"
                            f"Items: {json.dumps([item.model_dump() for item in order.items])}\n"
                            f"Dependencies: {json.dumps([dep.model_dump() for dep in order.dependencies])}\n"
                            f"Delivery zone: {order.delivery_zone}\n"
                            f"Episode history: {episode_history_summary}\n"
                            f"Strategy hint: {strategy_hint}\n"
                            "Return compact JSON only."
                        ),
                    },
                ],
                max_tokens=300,
                temperature=0,
            )
            content = response.choices[0].message.content if response.choices else ""
            payload = json.loads(content or "{}")
            plan = ParsedPlan(
                ordered_item_names=[
                    name for name in payload.get("ordered_item_names", []) if self._has_item(order, name)
                ],
                delivery_zone_name=payload.get("delivery_zone_name") or order.delivery_zone,
                priorities=[str(value) for value in payload.get("priorities", [])],
                ambiguity_notes=[str(value) for value in payload.get("ambiguity_notes", [])],
                steps=[
                    PlanStep(
                        action=str(step.get("action", "")),
                        target=str(step.get("target", "")),
                        zone=step.get("zone"),
                        notes=str(step.get("notes", "")),
                    )
                    for step in payload.get("steps", [])
                ],
                raw_response=content,
            )

            if plan.ordered_item_names:
                rationale = (
                    payload.get("ordering_rationale")
                    or payload.get("reasoning")
                    or payload.get("why")
                    or "LLM selected this order based on priority, dependency structure, and route efficiency."
                )
                plan.ambiguity_notes.append(f"LLM ordering rationale: {rationale}")

            if not plan.ordered_item_names:
                plan.ordered_item_names = fallback_plan.ordered_item_names
            if not plan.steps:
                plan.steps = fallback_plan.steps
            return plan
        except Exception:
            return fallback_plan

    @staticmethod
    def _has_item(order: Order, name: str) -> bool:
        return any(item.name == name for item in order.items)

    def heuristic_parse(self, order: Order) -> ParsedPlan:
        return self._heuristic_parse(order)

    def _heuristic_parse(self, order: Order) -> ParsedPlan:
        available_items = [item for item in order.items if item.in_stock and not item.delivered]
        ordered_items = self._dependency_priority_order(available_items, order)

        steps: List[PlanStep] = []
        for item in ordered_items:
            steps.append(
                PlanStep(
                    action="pick",
                    target=item.name,
                    zone=item.zone,
                    notes="Heuristic parser selected this item based on dependencies and priority.",
                )
            )
        steps.append(
            PlanStep(
                action="deliver",
                target=order.delivery_zone,
                zone=order.delivery_zone,
                notes="Complete the order at the designated staging zone.",
            )
        )

        ambiguity_notes = []
        if any(not item.in_stock for item in order.items):
            ambiguity_notes.append("Some requested items are out of stock; continue with remaining inventory.")

        return ParsedPlan(
            ordered_item_names=[item.name for item in ordered_items],
            steps=steps,
            delivery_zone_name=order.delivery_zone,
            priorities=[item.name for item in sorted(available_items, key=lambda item: -item.priority)],
            ambiguity_notes=ambiguity_notes,
            raw_response="heuristic_fallback",
        )

    def rank_orders(
        self,
        orders: Sequence[Order],
        episode_history_summary: str = "",
        strategy_hint: str = "",
    ) -> List[str]:
        fallback_ranking = self._heuristic_order_ranking(orders)
        if not orders:
            return []
        if not self._client or not self._model_name:
            return fallback_ranking

        try:
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Rank warehouse orders by which should be processed first. "
                            "Return compact JSON with keys order_ids and rationale."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Orders: {json.dumps([order.model_dump() for order in orders])}\n"
                            f"Episode history: {episode_history_summary}\n"
                            f"Strategy hint: {strategy_hint}\n"
                            "Prioritize deadlines, high-value items, and dependency risk."
                        ),
                    },
                ],
                max_tokens=200,
                temperature=0,
            )
            content = response.choices[0].message.content if response.choices else ""
            payload = json.loads(content or "{}")
            ranked_ids = [
                order_id
                for order_id in payload.get("order_ids", [])
                if any(order.order_id == order_id for order in orders)
            ]
            missing_ids = [order_id for order_id in fallback_ranking if order_id not in ranked_ids]
            return ranked_ids + missing_ids
        except Exception:
            return fallback_ranking

    @staticmethod
    def _dependency_priority_order(items: List[OrderItem], order: Order) -> List[OrderItem]:
        item_by_name: Dict[str, OrderItem] = {item.name: item for item in items}
        dependency_graph: Dict[str, set[str]] = {item.name: set() for item in items}

        for dependency in order.dependencies:
            if dependency.before_item in item_by_name and dependency.after_item in item_by_name:
                dependency_graph[dependency.after_item].add(dependency.before_item)

        try:
            topo_order = list(TopologicalSorter(dependency_graph).static_order())
        except Exception:
            topo_order = list(item_by_name.keys())

        topo_rank = {name: idx for idx, name in enumerate(topo_order)}
        return sorted(
            items,
            key=lambda item: (
                topo_rank.get(item.name, len(topo_rank)),
                -item.priority,
                item.is_fragile,
                item.name,
            ),
        )

    @staticmethod
    def _heuristic_order_ranking(orders: Sequence[Order]) -> List[str]:
        ranked = sorted(
            orders,
            key=lambda order: (
                order.deadline_steps if order.deadline_steps is not None else 10_000,
                -max((item.priority for item in order.items), default=0),
                -sum(item.priority for item in order.items),
                len(order.dependencies),
                order.order_id,
            ),
        )
        return [order.order_id for order in ranked]
