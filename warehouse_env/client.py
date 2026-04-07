from openenv.core.env_client import EnvClient
from openenv.core.client_types import StepResult
from .models import WarehouseAction, WarehouseObservation, WarehouseGameState

class WarehouseEnv(EnvClient[WarehouseAction, WarehouseObservation, WarehouseGameState]):
    def _step_payload(self, action: WarehouseAction) -> dict:
        return {"action_id": action.action_id}

    def _parse_result(self, payload: dict) -> StepResult:
        obs_data = payload.get("observation", {})
        return StepResult(
            observation=WarehouseObservation(
                done=payload.get("done", False),
                reward=payload.get("reward"),
                robot_pos=tuple(obs_data.get("robot_pos", [0, 0])),
                items_left=[tuple(it) for it in obs_data.get("items_left", [])],
                obstacles=[tuple(ob) for ob in obs_data.get("obstacles", [])],
                inventory=obs_data.get("inventory", 0),
                message=obs_data.get("message", ""),
                render=obs_data.get("render", "")
            ),
            reward=payload.get("reward"),
            done=payload.get("done", False)
        )

    def _parse_state(self, payload: dict) -> WarehouseGameState:
        return WarehouseGameState(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
            grid_size=tuple(payload.get("grid_size", [10, 10])),
            robot_pos=tuple(payload.get("robot_pos", [0, 0])),
            items=[tuple(it) for it in payload.get("items", [])],
            obstacles=[tuple(ob) for ob in payload.get("obstacles", [])],
            inventory=payload.get("inventory", 0),
            max_steps=payload.get("max_steps", 100)
        )
