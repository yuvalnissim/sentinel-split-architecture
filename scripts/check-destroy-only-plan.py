"""Refuse a cleanup plan that creates or updates any managed resource."""
import json
import sys


def check(plan):
    unexpected = [r["address"] for r in plan.get("resource_changes", [])
                  if r.get("mode", "managed") == "managed"
                  and r["change"]["actions"] not in (["delete"], ["no-op"])]
    if unexpected:
        raise ValueError("Cleanup plan is not destroy-only: " + ", ".join(unexpected))


if __name__ == "__main__":
    check(json.load(sys.stdin))
    print("Verified destroy-only managed resource actions.")
