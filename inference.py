import os
import sys
from collections import deque
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from openai import OpenAI

from warehouse_env.client import WarehouseEnv
from warehouse_env.models import WarehouseAction

API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN = os.getenv("HF_TOKEN")
API_KEY = os.getenv("API_KEY")
# Optional - if you use from_docker_image():
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")

Position = Tuple[int, int]

MOVE_DELTAS: Dict[int, Tuple[int, int]] = {
    0: (0, -1),
    1: (0, 1),
    2: (-1, 0),
    3: (1, 0),
}

DEFAULT_TASKS = ["easy_picking", "medium_picking", "hard_picking"]
DEFAULT_PORT_CANDIDATES = [7860, 8000, 8001, 8002]
MIN_SCORE = 0.0001
MAX_SCORE = 0.9999


def build_openai_client() -> OpenAI:
    api_key = API_KEY or HF_TOKEN
    if not api_key:
        raise RuntimeError("Missing required API_KEY or HF_TOKEN environment variable.")
    return OpenAI(api_key=api_key, base_url=API_BASE_URL)


def log_diagnostic(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit_start(task_id: str) -> None:
    print(f"[START] task={task_id}", flush=True)


def emit_step(
    task_id: str,
    step_count: int,
    reward: float,
    action_id: int,
    done: bool,
) -> None:
    print(
        "[STEP] "
        f"task={task_id} "
        f"step={step_count} "
        f"reward={reward:.4f} "
        f"action={action_id} "
        f"done={str(done).lower()}",
        flush=True,
    )


def emit_end(task_id: str, score: float, steps: int, status: str) -> None:
    bounded_score = min(MAX_SCORE, max(MIN_SCORE, score))
    print(
        f"[END] task={task_id} score={bounded_score:.4f} steps={steps} status={status}",
        flush=True,
    )


def emit_setup_failure(task_id: str, reason: str) -> None:
    emit_start(task_id)
    emit_step(task_id=task_id, step_count=0, reward=0.0, action_id=-1, done=False)
    emit_end(task_id, 0.0, 0, reason)


def resolve_model_name(client: OpenAI) -> str:
    requested_model = MODEL_NAME.strip()
    try:
        models = list(client.models.list())
    except Exception as exc:
        raise RuntimeError(f"Failed to list models through LiteLLM proxy: {exc}") from exc

    if not models:
        if requested_model:
            return requested_model
        raise RuntimeError("LiteLLM proxy returned no models.")

    model_ids = [model.id for model in models]
    if requested_model in model_ids:
        return requested_model

    log_diagnostic(
        f"[WARN] Requested MODEL_NAME '{requested_model}' not found. Using '{model_ids[0]}' instead."
    )
    return model_ids[0]


def ensure_llm_proxy_call(task_id: str) -> str:
    client = build_openai_client()
    model_name = resolve_model_name(client)

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise planning assistant for a warehouse robot.",
                },
                {
                    "role": "user",
                    "content": f"Confirm readiness for task {task_id} in one short sentence.",
                },
            ],
            max_tokens=16,
            temperature=0,
        )
    except Exception as exc:
        raise RuntimeError(f"LiteLLM proxy chat completion failed: {exc}") from exc

    content = response.choices[0].message.content if response.choices else ""
    log_diagnostic(
        f"[INFO] LiteLLM proxy call succeeded with model '{model_name}': {content or 'no content returned'}"
    )
    return model_name


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

    env_keys = [
        "OPENENV_BASE_URL",
        "OPENENV_URL",
        "BASE_URL",
        "SERVER_URL",
    ]
    for key in env_keys:
        value = os.getenv(key, "")
        if value:
            normalized = _normalize_base_url(value)
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)

    for key in ("OPENENV_PORT", "PORT"):
        value = os.getenv(key, "").strip()
        if value.isdigit():
            port = int(value)
            for host in ("127.0.0.1", "localhost"):
                url = f"http://{host}:{port}"
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
    probe_task = tasks[0] if tasks else "easy_picking"

    for candidate in _candidate_base_urls():
        try:
            client = WarehouseEnv(base_url=candidate, connect_timeout_s=2.0).sync()
            with client:
                client.reset(task_name=probe_task)
            log_diagnostic(f"[INFO] Connected to environment at: {candidate}")
            return candidate
        except Exception as exc:
            log_diagnostic(f"[WARN] Could not reach {candidate}: {exc}")

    log_diagnostic("[ERROR] Unable to connect to environment.")
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
    parents: Dict[Position, Tuple[Optional[Position], Optional[int]]] = {
        start: (None, None)
    }

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


def build_pick_plan(
    start: Position,
    items: Sequence[Position],
    grid_size: Position,
    obstacles: Sequence[Position],
) -> List[int]:
    remaining_items = list(items)
    if not remaining_items:
        return []

    points = [start, *remaining_items]
    pair_paths: Dict[Tuple[int, int], List[int]] = {}
    pair_costs: Dict[Tuple[int, int], int] = {}

    for i, src in enumerate(points):
        for j, dst in enumerate(points):
            if i == j:
                pair_paths[(i, j)] = []
                pair_costs[(i, j)] = 0
                continue
            path = shortest_path(src, dst, grid_size, obstacles)
            if path is None:
                raise RuntimeError(f"No valid path between {src} and {dst}")
            pair_paths[(i, j)] = path
            pair_costs[(i, j)] = len(path)

    item_count = len(remaining_items)
    full_mask = (1 << item_count) - 1
    dp: Dict[Tuple[int, int], int] = {}
    parent: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {}

    for item_idx in range(item_count):
        mask = 1 << item_idx
        dp[(mask, item_idx)] = pair_costs[(0, item_idx + 1)]
        parent[(mask, item_idx)] = None

    for mask in range(1, full_mask + 1):
        for last in range(item_count):
            state = (mask, last)
            if state not in dp:
                continue
            for nxt in range(item_count):
                if mask & (1 << nxt):
                    continue
                next_mask = mask | (1 << nxt)
                next_cost = dp[state] + pair_costs[(last + 1, nxt + 1)]
                next_state = (next_mask, nxt)
                if next_state not in dp or next_cost < dp[next_state]:
                    dp[next_state] = next_cost
                    parent[next_state] = state

    best_last = min(range(item_count), key=lambda idx: dp[(full_mask, idx)])

    order: List[int] = []
    state: Optional[Tuple[int, int]] = (full_mask, best_last)
    while state is not None:
        _, last = state
        order.append(last)
        state = parent[state]
    order.reverse()

    plan: List[int] = []
    current_point_idx = 0
    for item_idx in order:
        target_point_idx = item_idx + 1
        plan.extend(pair_paths[(current_point_idx, target_point_idx)])
        plan.append(4)
        current_point_idx = target_point_idx

    return plan


def execute_plan(env: WarehouseEnv, task_id: str) -> Tuple[float, int]:
    result = env.reset(task_name=task_id)
    obs = result.observation
    state = env.state()
    step_count = 0
    final_score = 0.0

    try:
        plan = build_pick_plan(
            start=obs.robot_pos,
            items=obs.items_left,
            grid_size=state.grid_size,
            obstacles=obs.obstacles,
        )
    except Exception as exc:
        log_diagnostic(f"[ERROR] Failed to build plan for task {task_id}: {exc}")
        return final_score, step_count

    for action_id in plan:
        try:
            result = env.step(WarehouseAction(action_id=action_id))
        except Exception as exc:
            log_diagnostic(f"[ERROR] Step error in task {task_id}: {exc}")
            break

        step_count += 1
        emit_step(
            task_id=task_id,
            step_count=step_count,
            reward=result.reward or 0.0,
            action_id=action_id,
            done=bool(result.done),
        )

        obs = result.observation
        if result.done:
            total_items = obs.inventory + len(obs.items_left)
            final_score = float(obs.inventory) / float(total_items) if total_items > 0 else 1.0
            break

    return final_score, step_count


def run_task(task_id: str, env_url: str) -> None:
    emit_start(task_id)
    final_score = 0.0
    step_count = 0
    status = "completed"

    try:
        client = WarehouseEnv(base_url=env_url, connect_timeout_s=5.0).sync()
        with client:
            final_score, step_count = execute_plan(client, task_id)
    except Exception as exc:
        status = "error"
        log_diagnostic(f"[ERROR] Environment connection or execution error in {task_id}: {exc}")
    else:
        if final_score < 1.0:
            status = "incomplete"

    emit_end(task_id, final_score, step_count, status)


def run_inference() -> None:
    tasks = DEFAULT_TASKS
    env_url = resolve_env_url(tasks)
    if not env_url:
        for task_id in tasks:
            emit_setup_failure(task_id, "env_unavailable")
        return

    try:
        model_name = ensure_llm_proxy_call(tasks[0])
        log_diagnostic(f"[INFO] Using LLM model: {model_name}")
    except Exception as exc:
        log_diagnostic(f"[ERROR] Unable to reach LiteLLM proxy: {exc}")
        for task_id in tasks:
            emit_setup_failure(task_id, "llm_unavailable")
        return

    for task_id in tasks:
        try:
            run_task(task_id, env_url)
        except Exception as exc:
            log_diagnostic(f"[ERROR] Unhandled exception in task {task_id}: {exc}")
            emit_setup_failure(task_id, "task_crash")


if __name__ == "__main__":
    try:
        run_inference()
    except Exception as exc:
        log_diagnostic(f"[FATAL] root inference crashed: {exc}")
        for task_id in DEFAULT_TASKS:
            emit_setup_failure(task_id, "fatal_crash")
