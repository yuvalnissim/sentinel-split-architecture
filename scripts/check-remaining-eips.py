"""Fail closed unless this incident's remaining managed objects are its EIPs."""
import json
import sys

EXPECTED = {
    'module.network["backend"].aws_eip.nat': "eipalloc-025f4933c6b09de75",
    'module.network["gateway"].aws_eip.nat': "eipalloc-0565f9a2884255c73",
}


def check_state(state, empty=False):
    bindings = {}
    for resource in state.get("resources", []):
        if resource["mode"] != "managed":
            continue
        for instance in resource.get("instances", []):
            if instance.get("deposed") or "index_key" in instance:
                raise ValueError("Unexpected indexed/deposed remaining resource")
            address = ".".join(filter(None, [resource.get("module"), resource["type"], resource["name"]]))
            if address in bindings:
                raise ValueError("Duplicate state binding")
            bindings[address] = instance["attributes"]["id"]
    if bindings != ({} if empty else EXPECTED):
        raise ValueError("Remaining state differs from the reviewed two EIPs")


def check_plan(plan):
    seen = set()
    for resource in plan.get("resource_changes", []):
        if resource.get("mode", "managed") != "managed":
            continue
        address = resource["address"]
        change = resource["change"]
        if address not in EXPECTED or address in seen:
            raise ValueError("Unexpected or duplicate managed resource in plan")
        before = change.get("before") or {}
        if change["actions"] != ["delete"] or before.get("id") != EXPECTED[address]:
            raise ValueError("Expected deletion of only the reviewed allocation")
        if before.get("association_id"):
            raise ValueError("Refreshed plan still contains an EIP association")
        seen.add(address)
    if seen != set(EXPECTED):
        raise ValueError("Plan must delete exactly the two remaining EIPs")


def check_addresses(response):
    addresses = response.get("Addresses", [])
    if len(addresses) != 2 or {a["AllocationId"] for a in addresses} != set(EXPECTED.values()):
        raise ValueError("AWS inventory differs from the reviewed EIPs")
    if any(a.get("AssociationId") or a.get("NetworkInterfaceId") or a.get("InstanceId") for a in addresses):
        raise ValueError("An EIP is still associated; manual review required")


if __name__ == "__main__":
    mode = sys.argv[1]
    document = json.load(sys.stdin)
    if mode == "plan":
        check_plan(document)
    elif mode == "addresses":
        check_addresses(document)
    elif mode in ("state", "empty"):
        check_state(document, empty=mode == "empty")
    else:
        raise ValueError("Unknown guard mode")
    print(f"Remaining EIP check passed: {mode}")
