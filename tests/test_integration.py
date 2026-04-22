import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from inference import build_execution_actions, build_item_sequence
from warehouse_env.client import WarehouseEnv
from warehouse_env.instruction_parser import InstructionParser
from warehouse_env.models import WarehouseAction
from warehouse_env.reward import clamp_score


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int, timeout_s: float = 15.0) -> None:
    deadline = time.time() + timeout_s
    root_url = f"http://127.0.0.1:{port}/"

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(root_url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)

    raise RuntimeError(f"Server on port {port} did not become ready in time.")


class TestIntegration:
    def test_env_client_heuristic_simple_order_flow(self):
        repo_root = Path(__file__).resolve().parents[1]
        port = _find_free_port()
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "warehouse_env.server.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            _wait_for_server(port)
            parser = InstructionParser()

            with WarehouseEnv(base_url=f"http://127.0.0.1:{port}", connect_timeout_s=5.0).sync() as env:
                result = env.reset(task_name="simple_order")
                observation = result.observation
                state = env.state()

                assert observation.current_order is not None
                plan = parser.parse(observation.current_order)
                item_sequence = build_item_sequence(
                    observation.current_order,
                    plan,
                    observation.robot_pos,
                    state.grid_size,
                    observation.obstacles,
                )
                actions = build_execution_actions(
                    observation.robot_pos,
                    item_sequence,
                    observation.current_order.delivery_position,
                    state.grid_size,
                    observation.obstacles,
                )

                final_observation = observation
                for action_id in actions:
                    step_result = env.step(WarehouseAction(action_id=action_id))
                    final_observation = step_result.observation
                    if step_result.done:
                        break

                final_state = env.state()
                assert final_observation.done
                assert 0.0001 <= clamp_score(final_state.score) <= 0.9999
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
