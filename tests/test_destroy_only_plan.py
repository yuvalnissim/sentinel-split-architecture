import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("destroy", Path(__file__).parents[1] / "scripts/check-destroy-only-plan.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DestroyOnlyTests(unittest.TestCase):
    def test_delete_and_data_read_pass(self):
        module.check({"resource_changes": [
            {"address": "aws_vpc.this", "change": {"actions": ["delete"]}},
            {"address": "data.aws_x.this", "mode": "data", "change": {"actions": ["read"]}}]})

    def test_creation_update_and_replacement_fail(self):
        for actions in (["create"], ["update"], ["delete", "create"]):
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                module.check({"resource_changes": [{"address": "aws_vpc.this", "change": {"actions": actions}}]})
