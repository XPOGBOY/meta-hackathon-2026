from __future__ import annotations

from warehouse_env.server.environment import WarehouseEnvironment
from warehouse_env.instruction_parser import InstructionParser
from warehouse_env.models import WarehouseAction

def test_end_to_end_integration():
    """
    Tests the full loop:
    1. Spin up the environment
    2. Reset to 'simple_order'
    3. Use the heuristic parser to get an optimal plan
    4. Ensure the episode doesn't crash during a step
    """
    env = WarehouseEnvironment()
    parser = InstructionParser()
    
    # 1. Reset
    observation = env.reset(task_name="simple_order")
    assert observation is not None
    assert observation.current_order is not None
    
    # 2. Parse instruction
    plan = parser.heuristic_parse(observation.current_order)
    assert len(plan.ordered_item_names) > 0
    assert plan.delivery_zone_name is not None
    
    # 3. Step in the environment (Dummy step to ensure no crash)
    step_observation = env.step(WarehouseAction(action_id=0, plan_response=plan.model_dump_json()))
    assert step_observation is not None
    
    # 4. Check that state tracking is initialized correctly
    state = env.state
    assert state.step_count == 1
    assert state.max_steps == 45
    assert state.task_name == "simple_order"
    assert state.score >= 0.0001  # Score clamped
