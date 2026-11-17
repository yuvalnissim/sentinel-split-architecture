import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("eips", Path(__file__).parents[1] / "scripts/check-remaining-eips.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RemainingEipTests(unittest.TestCase):
    def state(self):
        return {"resources": [{"mode": "managed", "module": address.rsplit(".aws_eip.", 1)[0],
                "type": "aws_eip", "name": "nat", "instances": [{"attributes": {"id": allocation}}]}
                for address, allocation in module.EXPECTED.items()]}

    def plan(self):
        return {"resource_changes": [{"mode": "managed", "address": address,
                "change": {"actions": ["delete"], "before": {"id": allocation, "association_id": None}}}
                for address, allocation in module.EXPECTED.items()]}

    def test_exact_remaining_state_and_delete_plan_pass(self):
        module.check_state(self.state())
        module.check_plan(self.plan())

    def test_extra_managed_state_fails(self):
        state = self.state()
        state["resources"].append({"mode": "managed", "type": "aws_instance", "name": "other",
                                  "instances": [{"attributes": {"id": "i-other"}}]})
        with self.assertRaises(ValueError):
            module.check_state(state)

    def test_unknown_allocation_and_missing_deletion_fail(self):
        plan = self.plan()
        plan["resource_changes"][0]["change"]["before"]["id"] = "eipalloc-other"
        with self.assertRaises(ValueError):
            module.check_plan(plan)
        plan = self.plan()
        plan["resource_changes"].pop()
        with self.assertRaises(ValueError):
            module.check_plan(plan)

    def test_association_and_replacement_fail(self):
        for change in ({"association_id": "eipassoc-still-used"}, {"actions": ["delete", "create"]}):
            plan = self.plan()
            entry = plan["resource_changes"][0]["change"]
            if "actions" in change:
                entry["actions"] = change["actions"]
            else:
                entry["before"].update(change)
            with self.assertRaises(ValueError):
                module.check_plan(plan)

    def test_live_addresses_must_be_exact_and_unattached(self):
        addresses = {"Addresses": [{"AllocationId": a} for a in module.EXPECTED.values()]}
        module.check_addresses(addresses)
        for key in ("AssociationId", "NetworkInterfaceId", "InstanceId"):
            associated = copy.deepcopy(addresses)
            associated["Addresses"][0][key] = "still-used"
            with self.assertRaises(ValueError):
                module.check_addresses(associated)

    def test_empty_guard_rejects_remaining_allocations(self):
        module.check_state({"resources": []}, empty=True)
        with self.assertRaises(ValueError):
            module.check_state(self.state(), empty=True)
