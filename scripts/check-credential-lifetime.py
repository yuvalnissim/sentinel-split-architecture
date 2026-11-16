"""Fail before Terraform writes state when copied AWS credentials expire too soon."""
import datetime as dt
import os
import sys


def remaining_seconds(expiration, now=None):
    if not expiration:
        raise ValueError("Set bootstrap environment variable AWS_CREDENTIAL_EXPIRATION to the expiration of the exact session stored in secrets")
    expiry = dt.datetime.fromisoformat(expiration.replace("Z", "+00:00"))
    if expiry.tzinfo is None:
        raise ValueError("Credential expiration must include a timezone")
    return (expiry - (now or dt.datetime.now(dt.timezone.utc))).total_seconds()


if __name__ == "__main__":
    minimum = int(sys.argv[1]) if len(sys.argv) > 1 else 3300
    try:
        remaining = remaining_seconds(os.environ.get("AWS_CREDENTIAL_EXPIRATION", ""))
        if remaining < minimum:
            raise ValueError(f"Credentials need at least {minimum // 60} minutes remaining; only {max(0, int(remaining // 60))} remain. Do not use a static 15-minute aws login export for provisioning.")
    except ValueError as error:
        raise SystemExit(str(error))
    print(f"Credential lifetime check passed ({int(remaining // 60)} minutes remaining).")
