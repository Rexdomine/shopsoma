"""Fail closed unless this process has loopback-only network isolation."""

import errno
import json
import socket
from pathlib import Path


def verify():
    interfaces = sorted(name for _, name in socket.if_nameindex())
    if interfaces != ["lo"]:
        raise RuntimeError("Containment requires exactly the loopback interface")
    results = []
    for family, address in [
        (socket.AF_INET, "1.1.1.1"),
        (socket.AF_INET6, "2606:4700:4700::1111"),
    ]:
        with socket.socket(family, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            try:
                connection.connect((address, 443))
            except OSError as exc:
                if exc.errno not in (
                    errno.ENETUNREACH,
                    errno.EHOSTUNREACH,
                    errno.EAFNOSUPPORT,
                ):
                    raise RuntimeError(
                        "Containment is unproven (timeout/refusal is insufficient)"
                    ) from exc
                results.append({"family": family.name, "denied_errno": exc.errno})
            else:
                raise RuntimeError("External egress succeeded")
    return {"interfaces": interfaces, "external_probes": results, "passed": True}


if __name__ == "__main__":
    Path("/evidence/containment.json").write_text(json.dumps(verify(), indent=2))
