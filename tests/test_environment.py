from warehouse_env.models import WarehouseAction
from warehouse_env.server.environment import WarehouseEnvironment


class TestEnvironment:
    def test_reset_simple_order(self):
        env = WarehouseEnvironment()
        obs = env.reset(task_name="simple_order")

        assert not obs.done
        assert obs.robot_pos == (0, 0)
        assert obs.current_order is not None
        assert len(obs.current_order.items) == 2

    def test_reset_all_tasks(self):
        env = WarehouseEnvironment()

        for task in ["simple_order", "multi_step_order", "order_queue", "adaptive_fulfillment"]:
            obs = env.reset(task_name=task)
            assert not obs.done
            assert obs.current_order is not None

    def test_move_actions(self):
        env = WarehouseEnvironment()
        env.reset(seed=0, task_name="simple_order")

        obs = env.step(WarehouseAction(action_id=3))
        assert obs.robot_pos[0] >= 1

        obs = env.step(WarehouseAction(action_id=1))
        assert obs.robot_pos[1] >= 1

    def test_invalid_pick(self):
        env = WarehouseEnvironment()
        env.reset(task_name="simple_order")

        obs = env.step(WarehouseAction(action_id=4))
        assert "No requested item" in obs.message or "No active order" in obs.message

    def test_score_bounds(self):
        env = WarehouseEnvironment()
        env.reset(task_name="simple_order")

        for _ in range(50):
            obs = env.step(WarehouseAction(action_id=3))
            if obs.done:
                break

        state = env.state
        assert 0.0001 <= state.score <= 0.9999
