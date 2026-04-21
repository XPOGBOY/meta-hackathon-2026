from __future__ import annotations

import json
import os
from collections import Counter, deque
from statistics import mean
from typing import Deque, List, Optional, Sequence

from openai import OpenAI
from pydantic import BaseModel, Field


class EpisodeRecord(BaseModel):
    task_name: str
    score: float
    steps_taken: int
    orders_completed: int
    total_orders: int
    failure_reasons: List[str] = Field(default_factory=list)
    priority_compliance: float = 1.0
    efficiency_ratio: float = 0.0


class EpisodeMemory:
    def __init__(self, max_episodes: int = 25):
        self._records: Deque[EpisodeRecord] = deque(maxlen=max_episodes)

    def add(self, record: EpisodeRecord) -> None:
        self._records.append(record)

    def list(self) -> List[EpisodeRecord]:
        return list(self._records)

    def last_n(self, count: int) -> List[EpisodeRecord]:
        if count <= 0:
            return []
        return list(self._records)[-count:]

    def __len__(self) -> int:
        return len(self._records)


class PerformanceTracker:
    def __init__(self, max_episodes: int = 25):
        self.memory = EpisodeMemory(max_episodes=max_episodes)

    def record_episode(self, record: EpisodeRecord) -> None:
        self.memory.add(record)

    def recent_average_score(self, count: int = 3) -> float:
        recent = self.memory.last_n(count)
        if not recent:
            return 0.0
        return mean(record.score for record in recent)

    def baseline_score(self) -> float:
        records = self.memory.list()
        if not records:
            return 0.0
        sample = records[: min(5, len(records))]
        return mean(record.score for record in sample)

    def completion_rate(self, count: int = 5) -> float:
        recent = self.memory.last_n(count)
        if not recent:
            return 0.0
        return mean(
            record.orders_completed / float(max(record.total_orders, 1)) for record in recent
        )

    def summary(self, count: int = 5) -> str:
        recent = self.memory.last_n(count)
        if not recent:
            return "No prior episodes recorded yet."

        avg_score = mean(record.score for record in recent)
        avg_steps = mean(record.steps_taken for record in recent)
        avg_completion = mean(
            record.orders_completed / float(max(record.total_orders, 1)) for record in recent
        )
        avg_priority = mean(record.priority_compliance for record in recent)

        failure_counts = Counter(
            reason
            for record in recent
            for reason in record.failure_reasons
            if reason
        )
        top_failure = failure_counts.most_common(1)[0][0] if failure_counts else "none"

        return (
            f"Recent episodes: avg_score={avg_score:.3f}, avg_steps={avg_steps:.1f}, "
            f"completion_rate={avg_completion:.2f}, priority_compliance={avg_priority:.2f}, "
            f"top_failure={top_failure}."
        )

    def records_as_json(self, count: int = 5) -> str:
        records = [record.model_dump() for record in self.memory.last_n(count)]
        return json.dumps(records, separators=(",", ":"))


class CurriculumController:
    LEVELS = [
        "simple_order",
        "multi_step_order",
        "order_queue",
        "adaptive_fulfillment",
    ]

    def __init__(self, initial_level: str = "simple_order"):
        self._index = self.LEVELS.index(initial_level) if initial_level in self.LEVELS else 0

    @property
    def current_level(self) -> str:
        return self.LEVELS[self._index]

    def update(self, tracker: PerformanceTracker) -> str:
        recent = tracker.memory.last_n(3)
        if len(recent) < 3:
            return self.current_level

        if all(record.score > 0.8 for record in recent) and self._index < len(self.LEVELS) - 1:
            self._index += 1
        elif all(record.score < 0.35 for record in recent) and self._index > 0:
            self._index -= 1
        return self.current_level


class StrategyAdapter:
    def __init__(self, client: Optional[OpenAI] = None, model_name: Optional[str] = None):
        self._client = client
        self._model_name = model_name

    @classmethod
    def from_env(cls) -> "StrategyAdapter":
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

    def suggest(self, tracker: PerformanceTracker, count: int = 3) -> str:
        recent = tracker.memory.last_n(count)
        if not recent:
            return "No prior episodes yet. Start by finishing high-priority items before delivering."

        heuristic = self._heuristic_hint(recent)
        if not self._client or not self._model_name:
            return heuristic

        try:
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are helping a warehouse planning agent improve after recent episodes. "
                            "Return one concise planning hint."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Recent history: {tracker.records_as_json(count=count)}\n"
                            f"Current heuristic hint: {heuristic}"
                        ),
                    },
                ],
                max_tokens=60,
                temperature=0.1,
            )
            content = response.choices[0].message.content if response.choices else ""
            return (content or heuristic).strip()
        except Exception:
            return heuristic

    @staticmethod
    def _heuristic_hint(records: Sequence[EpisodeRecord]) -> str:
        failure_counts = Counter(
            reason
            for record in records
            for reason in record.failure_reasons
            if reason
        )
        most_common = failure_counts.most_common(1)[0][0] if failure_counts else ""

        if most_common == "deadline_missed":
            return "Recent runs missed deadlines. Prioritize closer high-priority items and deliver sooner."
        if most_common == "dependency_violation":
            return "Recent runs broke dependency order. Respect prerequisite items before fragile follow-ups."
        if most_common == "delivery_error":
            return "Recent runs lost time at delivery. Confirm the staging zone before taking the deliver action."

        avg_priority = mean(record.priority_compliance for record in records)
        if avg_priority < 0.8:
            return "Improve priority compliance by collecting the highest-priority eligible item first."

        return "Keep the route compact and bundle pickups so the final delivery happens with a full valid load."
