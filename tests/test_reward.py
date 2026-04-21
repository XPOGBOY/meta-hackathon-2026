from warehouse_env.models import OrderItem, WarehouseGameState
from warehouse_env.reward import RewardContext, clamp_score, compute_episode_score, compute_reward


class TestReward:
    def test_clamp_score(self):
        assert clamp_score(0.0) == 0.0001
        assert clamp_score(1.0) == 0.9999
        assert clamp_score(0.5) == 0.5

    def test_pickup_reward_scales_with_priority(self):
        state = WarehouseGameState()
        low_priority = RewardContext(
            picked_item=OrderItem(name="a", position=(0, 0), zone="A", priority=1)
        )
        high_priority = RewardContext(
            picked_item=OrderItem(name="b", position=(0, 0), zone="A", priority=5)
        )

        r_low = compute_reward(state, 4, low_priority)
        r_high = compute_reward(state, 4, high_priority)
        assert r_high > r_low

    def test_dependency_violation_penalty(self):
        state = WarehouseGameState()
        correct = RewardContext(picked_in_correct_order=True)
        violation = RewardContext(picked_out_of_order=True)

        r_correct = compute_reward(state, 4, correct)
        r_violation = compute_reward(state, 4, violation)
        assert r_correct > r_violation

    def test_episode_score_is_clamped(self):
        score = compute_episode_score(
            total_orders=3,
            completed_orders=3,
            priority_actions=1,
            priority_compliant_actions=1,
            steps_taken=1,
            max_steps=100,
            baseline_score=0.1,
            current_average_score=1.0,
        )
        assert 0.0001 <= score <= 0.9999
