import datetime as dt
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("recovery", Path(__file__).resolve().parents[1] / "scripts/recover-sentinel-state.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def route_tables():
    return {
        f'module.network["{domain}"].aws_route_table.private["{az}"]': {"id": f"rtb-{domain}-{az}"}
        for domain in recovery.VPCS for az in ("a", "b")
    }


class RecoveryTests(unittest.TestCase):
    def test_initial_inventory_has_ten_missing_bindings(self):
        self.assertEqual(len(recovery.missing_imports(route_tables())), 10)

    def test_already_imported_resources_are_skipped(self):
        instances = route_tables()
        for address, _, expected in recovery.candidates(instances):
            instances[address] = expected
        self.assertEqual(recovery.missing_imports(instances), [])

    def test_wrong_existing_mapping_aborts(self):
        instances = route_tables()
        instances['module.eks["gateway"].aws_eks_cluster.this'] = {"name": "other-cluster"}
        with self.assertRaisesRegex(RuntimeError, "mapping differs"):
            recovery.missing_imports(instances)

    def test_routes_use_table_and_destination_import_ids(self):
        routes = [item for item in recovery.candidates(route_tables()) if ".aws_route." in item[0]]
        self.assertEqual(len(routes), 4)
        self.assertTrue(all(item[1].endswith("_0.0.0.0/0") for item in routes))

    def test_empty_resource_and_indexed_instances_are_handled(self):
        state = {"resources": [
            {"mode": "managed", "module": 'module.eks["gateway"]', "type": "aws_eks_cluster", "name": "this", "instances": []},
            {"mode": "managed", "type": "aws_iam_role", "name": "installer", "instances": [{"index_key": 0, "attributes": {"id": "role"}}]},
            {"mode": "data", "type": "ignored", "name": "data", "instances": []},
        ]}
        self.assertEqual(recovery.state_instances(state), {"aws_iam_role.installer[0]": {"id": "role"}})

    def test_deposed_duplicate_bindings_abort(self):
        state = {"resources": [{"mode": "managed", "type": "aws_instance", "name": "runner",
                                "instances": [{"attributes": {}}, {"attributes": {}}]}]}
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            recovery.state_instances(state)

    def test_credential_expiry_uses_timezone(self):
        now = dt.datetime(2026, 11, 16, 10, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(recovery.remaining_seconds("2026-11-16T12:15:00+02:00", now), 900)
        self.assertEqual(recovery.remaining_seconds("2026-11-16T09:59:00Z", now), -60)
        with self.assertRaises(ValueError):
            recovery.remaining_seconds("2026-11-16T12:15:00", now)


if __name__ == "__main__":
    unittest.main()
