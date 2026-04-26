"""Self-improvement loop: episode memory, curriculum, and LLM strategy hints.

This module is the "brain that watches the brain". It tracks every finished
episode in a fixed-size memory buffer, exposes rolling statistics that feed
both the reward shaping and the LLM prompt context, and decides when to
promote/demote the agent along a curriculum of warehouse tasks.

The design rests on three small, composable pieces:

* :class:`EpisodeMemory` — a bounded ``deque`` of :class:`EpisodeRecord`
  objects. The bound matters: the loop is *online*, so we want statistics
  that reflect the agent's *current* behaviour, not its entire history.
* :class:`PerformanceTracker` — pure-functional reductions over the memory
  (averages, completion rate, top failure mode, JSON dump for prompts).
* :class:`CurriculumController` and :class:`StrategyAdapter` — two policies
  that *consume* the tracker. The curriculum changes which task the agent
  trains on; the strategy adapter changes the natural-language hint that is
  injected back into the LLM instruction parser. Together they close the
  feedback loop: failures observed in past episodes literally rewrite the
  prompt and the difficulty of the next episode.
"""

from __future__ import annotations

import json
import os
from collections import Counter, deque
from statistics import mean
from typing import Deque, List, Optional, Sequence

from openai import OpenAI
from pydantic import BaseModel, Field


class EpisodeRecord(BaseModel):
    """Snapshot of a single completed episode.

    Records are immutable once written and small enough that we can keep
    dozens of them in memory and JSON-serialize the whole window into an
    LLM prompt without worrying about token cost.

    Attributes:
        task_name: Curriculum task this episode ran on.
        score: Final clamped score for the episode (in
            ``[reward.MIN_SCORE, reward.MAX_SCORE]``).
        steps_taken: Total environment steps consumed.
        orders_completed: Orders that were fully delivered.
        total_orders: Orders the episode was supposed to fulfill.
        failure_reasons: De-duplicated list of failure tags
            (e.g. ``"deadline_missed"``, ``"dependency_violation"``).
        priority_compliance: Fraction of pick actions that targeted the
            highest-priority eligible item at the time.
        efficiency_ratio: Steps left over relative to ``max_steps``.
    """

    task_name: str
    score: float
    steps_taken: int
    orders_completed: int
    total_orders: int
    failure_reasons: List[str] = Field(default_factory=list)
    priority_compliance: float = 1.0
    efficiency_ratio: float = 0.0


class EpisodeMemory:
    """Fixed-capacity FIFO buffer of :class:`EpisodeRecord` objects.

    Wrapping the underlying ``deque`` lets us swap out the storage layer
    later (e.g. to persist to disk or stream to W&B) without touching the
    callers.
    """

    def __init__(self, max_episodes: int = 25) -> None:
        """Initialize the memory with a hard upper bound on retained episodes.

        Args:
            max_episodes: Maximum number of episodes to retain. When the
                buffer is full, appending a new record evicts the oldest
                one. Default of ``25`` is large enough for stable rolling
                stats and small enough to fit comfortably in an LLM prompt.
        """
        self._records: Deque[EpisodeRecord] = deque(maxlen=max_episodes)

    def add(self, record: EpisodeRecord) -> None:
        """Append an episode record, evicting the oldest if at capacity."""
        self._records.append(record)

    def list(self) -> List[EpisodeRecord]:
        """Return a defensive copy of every retained record, oldest first."""
        return list(self._records)

    def last_n(self, count: int) -> List[EpisodeRecord]:
        """Return the most recent ``count`` records (or fewer if not enough yet).

        Args:
            count: Number of records to return. Non-positive values yield an
                empty list.

        Returns:
            A list of up to ``count`` records, oldest-to-newest.
        """
        if count <= 0:
            return []
        return list(self._records)[-count:]

    def __len__(self) -> int:
        return len(self._records)


class PerformanceTracker:
    """Rolling statistics over an :class:`EpisodeMemory` buffer.

    Every method on this class is a *read-only reduction* over the memory.
    The tracker never mutates records — it only summarises them — which is
    why it can be safely shared between the reward function, the LLM
    prompt builder, and the curriculum controller.
    """

    def __init__(self, max_episodes: int = 25) -> None:
        """Build a tracker backed by an :class:`EpisodeMemory` of the given size.

        Args:
            max_episodes: Capacity passed straight through to the underlying
                memory buffer.
        """
        self.memory = EpisodeMemory(max_episodes=max_episodes)

    def record_episode(self, record: EpisodeRecord) -> None:
        """Append a finished episode to the tracker's memory.

        This is the single write-path into the self-improvement loop. The
        environment calls it exactly once per episode, at finalize time.
        """
        # The memory loop hinges on this single append: every downstream
        # statistic (baseline, averages, top failure) is just a reduction
        # over the deque, so as soon as we record an episode the next one
        # automatically sees an updated context.
        self.memory.add(record)

    def recent_average_score(self, count: int = 3) -> float:
        """Mean episode score over the last ``count`` episodes.

        Args:
            count: How many of the most recent episodes to average.

        Returns:
            The mean score, or ``0.0`` if no episodes have been recorded.
        """
        recent = self.memory.last_n(count)
        if not recent:
            return 0.0
        return mean(record.score for record in recent)

    def baseline_score(self) -> float:
        """Mean score over the *first* few recorded episodes.

        Returns:
            The mean score of up to the first 5 episodes, used as the
            "starting line" against which improvement is measured. Returns
            ``0.0`` before the agent has run anything.
        """
        records = self.memory.list()
        if not records:
            return 0.0
        sample = records[: min(5, len(records))]
        return mean(record.score for record in sample)

    def completion_rate(self, count: int = 5) -> float:
        """Mean fraction of orders completed across the last ``count`` episodes.

        Args:
            count: How many of the most recent episodes to include.

        Returns:
            A value in ``[0, 1]``, or ``0.0`` if no episodes have run.
        """
        recent = self.memory.last_n(count)
        if not recent:
            return 0.0
        return mean(
            record.orders_completed / float(max(record.total_orders, 1)) for record in recent
        )

    def summary(self, count: int = 5) -> str:
        """Human-readable rolling summary suitable for an LLM system prompt.

        This string is the bridge between the algorithmic memory and the
        semantic LLM: it gets injected verbatim into the instruction
        parser so the next plan is conditioned on the *agent's own past
        failures*. That single dependency is what makes the whole loop
        self-improving.

        Args:
            count: Window of recent episodes to summarise.

        Returns:
            A compact string describing average score/steps, completion
            rate, priority compliance, and the most common failure mode.
        """
        recent = self.memory.last_n(count)
        if not recent:
            return "No prior episodes recorded yet."

        avg_score = mean(record.score for record in recent)
        avg_steps = mean(record.steps_taken for record in recent)
        avg_completion = mean(
            record.orders_completed / float(max(record.total_orders, 1)) for record in recent
        )
        avg_priority = mean(record.priority_compliance for record in recent)

        # Counter over flattened failure tags lets the LLM see the *modal*
        # failure (e.g. "you keep missing deadlines") instead of a noisy
        # per-episode dump.
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
        """Serialize the last ``count`` episodes to compact JSON.

        Used by :class:`StrategyAdapter` to give the LLM full structured
        access to recent history (rather than just the prose summary).

        Args:
            count: Window of recent episodes to serialize.

        Returns:
            A compact JSON array of episode-record dicts.
        """
        records = [record.model_dump() for record in self.memory.last_n(count)]
        return json.dumps(records, separators=(",", ":"))


class CurriculumController:
    """Promote/demote the agent along a fixed curriculum of warehouse tasks.

    Promotion happens after three consecutive strong episodes
    (``score > 0.8``); demotion happens after three consecutive weak ones
    (``score < 0.35``). The conservative "three in a row" gate keeps the
    curriculum from oscillating on noise.
    """

    LEVELS: List[str] = [
        "simple_order",
        "multi_step_order",
        "order_queue",
        "adaptive_fulfillment",
    ]

    def __init__(self, initial_level: str = "simple_order") -> None:
        """Initialize the controller at a specific curriculum level.

        Args:
            initial_level: The level name to start at. Must be one of
                :attr:`LEVELS`; unknown values fall back to the easiest level.
        """
        self._index = self.LEVELS.index(initial_level) if initial_level in self.LEVELS else 0

    @property
    def current_level(self) -> str:
        """The curriculum level the agent should train on right now."""
        return self.LEVELS[self._index]

    def update(self, tracker: PerformanceTracker) -> str:
        """Decide whether to promote, demote, or hold the curriculum level.

        Args:
            tracker: The shared :class:`PerformanceTracker`.

        Returns:
            The (possibly updated) curriculum level name.
        """
        recent = tracker.memory.last_n(3)
        if len(recent) < 3:
            return self.current_level

        # "Three in a row" is intentional anti-noise: a single great or
        # terrible episode should not move the curriculum.
        if all(record.score > 0.8 for record in recent) and self._index < len(self.LEVELS) - 1:
            self._index += 1
        elif all(record.score < 0.35 for record in recent) and self._index > 0:
            self._index -= 1
        return self.current_level


class StrategyAdapter:
    """Turn recent failure history into a one-line strategy hint for the LLM.

    The adapter has two modes. With an ``OPENAI``-compatible client wired
    up, it asks an LLM for a concise hint conditioned on the JSON history.
    Without a client (or on any failure), it falls back to a deterministic
    rule-based hint keyed off the modal failure mode. Either way, callers
    get a short string they can splice into the next plan's prompt.
    """

    def __init__(
        self,
        client: Optional[OpenAI] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """Create an adapter, optionally bound to a chat-completions client.

        Args:
            client: An :class:`openai.OpenAI` client (or compatible). If
                ``None``, the adapter operates in offline heuristic mode.
            model_name: The model id to call. Required when ``client`` is
                set; ignored otherwise.
        """
        self._client = client
        self._model_name = model_name

    @classmethod
    def from_env(cls) -> "StrategyAdapter":
        """Construct an adapter from process environment variables.

        Reads ``API_BASE_URL``, ``HF_TOKEN``/``API_KEY`` and ``MODEL_NAME``.
        If no credentials are present, or the model listing fails for any
        reason, the returned adapter runs entirely on the heuristic path.
        """
        base_url = os.getenv("API_BASE_URL", "https://api.openai.com/v1").strip()
        api_key = (os.getenv("HF_TOKEN") or os.getenv("API_KEY") or "").strip()
        if not api_key:
            return cls()

        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            available_models = list(client.models.list())
            requested = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()
            # Prefer the user's explicit pick when available; otherwise use
            # whatever the endpoint lists first so we degrade gracefully on
            # custom inference servers (e.g. HF Inference Endpoints).
            model_name = (
                requested
                if any(model.id == requested for model in available_models)
                else available_models[0].id
            )
            return cls(client=client, model_name=model_name)
        except Exception:
            return cls()

    def suggest(self, tracker: PerformanceTracker, count: int = 3) -> str:
        """Produce a one-line strategy hint from the last few episodes.

        Args:
            tracker: The shared :class:`PerformanceTracker`.
            count: Window of recent episodes to consider.

        Returns:
            A short natural-language hint. Always non-empty.
        """
        recent = tracker.memory.last_n(count)
        if not recent:
            return "No prior episodes yet. Start by finishing high-priority items before delivering."

        heuristic_hint = self._heuristic_hint(recent)
        if not self._client or not self._model_name:
            return heuristic_hint

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
                            f"Current heuristic hint: {heuristic_hint}"
                        ),
                    },
                ],
                max_tokens=60,
                temperature=0.1,
            )
            content = response.choices[0].message.content if response.choices else ""
            return (content or heuristic_hint).strip()
        except Exception:
            # Network hiccups, rate limits, or malformed responses must
            # never break training — fall back to the deterministic hint.
            return heuristic_hint

    @staticmethod
    def _heuristic_hint(records: Sequence[EpisodeRecord]) -> str:
        """Deterministic fallback hint keyed off the modal failure mode."""
        failure_counts = Counter(
            reason
            for record in records
            for reason in record.failure_reasons
            if reason
        )
        most_common_failure = failure_counts.most_common(1)[0][0] if failure_counts else ""

        if most_common_failure == "deadline_missed":
            return "Recent runs missed deadlines. Prioritize closer high-priority items and deliver sooner."
        if most_common_failure == "dependency_violation":
            return "Recent runs broke dependency order. Respect prerequisite items before fragile follow-ups."
        if most_common_failure == "delivery_error":
            return "Recent runs lost time at delivery. Confirm the staging zone before taking the deliver action."

        avg_priority = mean(record.priority_compliance for record in records)
        if avg_priority < 0.8:
            return "Improve priority compliance by collecting the highest-priority eligible item first."

        return "Keep the route compact and bundle pickups so the final delivery happens with a full valid load."
