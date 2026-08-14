"""CLI entrypoint for SEC-004 security posture audit."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from backend.core.config import settings
from backend.db.session import SessionLocal
from backend.modules.admin.security_posture import run_security_posture_audit


async def _run(*, config_only: bool) -> int:
    if config_only:
        report = await run_security_posture_audit(None)
    else:
        async with SessionLocal() as session:
            report = await run_security_posture_audit(session)

    payload = report.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    critical = payload["summary"].get("critical", 0)
    high = payload["summary"].get("high", 0)
    if critical or high:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Troop security posture audit (SEC-004).")
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="Skip database-backed checks (environment settings only).",
    )
    args = parser.parse_args()
    if args.config_only:
        return asyncio.run(_run(config_only=True))
    if not settings.DATABASE_URL:
        print("DATABASE_URL is required unless --config-only is set.", file=sys.stderr)
        return 2
    return asyncio.run(_run(config_only=False))


if __name__ == "__main__":
    raise SystemExit(main())
