"""Render discovered environment values; leave the checked-in manifest unchanged."""
import os
import re
import sys
from pathlib import Path


def render(domain, source, values):
    if domain == "backend":
        marker = "REPLACE_BACKEND_ALB_SECURITY_GROUP_ID"
        value = values.get("BACKEND_ALB_SECURITY_GROUP_ID", "")
        if not re.fullmatch(r"sg-(?:[0-9a-f]{8}|[0-9a-f]{17})", value):
            raise ValueError("Expected exactly one valid backend ALB security group ID")
    elif domain == "gateway":
        marker = "http://backend.invalid"
        value = values.get("BACKEND_URL", "")
        if not re.fullmatch(r"http://internal-[a-z0-9-]+\.eu-north-1\.elb\.amazonaws\.com", value):
            raise ValueError("Expected the internal backend ALB HTTP hostname in eu-north-1")
    else:
        raise ValueError("Expected backend or gateway")
    if source.count(marker) != 1:
        raise ValueError("Expected exactly one environment placeholder")
    return source.replace(marker, value)


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Usage: render-environment.py backend|gateway SOURCE DESTINATION")
    domain, source, destination = sys.argv[1:]
    rendered = render(domain, Path(source).read_text(), os.environ)
    Path(destination).write_text(rendered)


if __name__ == "__main__":
    main()
