from warehouse_env.instruction_parser import InstructionParser
from warehouse_env.models import Order, OrderDependency, OrderItem


class TestInstructionParser:
    def test_heuristic_parse_respects_dependencies(self):
        parser = InstructionParser()
        order = Order(
            order_id="test-1",
            instruction_text="Pick A then B",
            items=[
                OrderItem(name="B", position=(1, 1), zone="A", priority=5),
                OrderItem(name="A", position=(2, 2), zone="B", priority=1),
            ],
            delivery_zone="STAGE_1",
            delivery_position=(0, 4),
            dependencies=[OrderDependency(before_item="A", after_item="B")],
        )

        plan = parser.parse(order)
        assert plan.ordered_item_names.index("A") < plan.ordered_item_names.index("B")

    def test_order_ranking_prefers_shorter_deadline(self):
        parser = InstructionParser()
        orders = [
            Order(
                order_id="late",
                instruction_text="Later deadline",
                items=[OrderItem(name="x", position=(1, 1), zone="A", priority=3)],
                delivery_zone="STAGE_1",
                delivery_position=(0, 4),
                deadline_steps=20,
            ),
            Order(
                order_id="urgent",
                instruction_text="Urgent deadline",
                items=[OrderItem(name="y", position=(2, 2), zone="B", priority=3)],
                delivery_zone="STAGE_2",
                delivery_position=(4, 4),
                deadline_steps=5,
            ),
        ]

        ranking = parser.rank_orders(orders)
        assert ranking[0] == "urgent"
