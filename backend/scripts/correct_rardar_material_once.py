"""Private Rardar material recovery: read-only preview or operator-granted apply.

The apply grant is supplied on stdin by a root-controlled host wrapper. The
application's writable data mount is not an authorization source.
"""

import argparse
import asyncio
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--mode", choices=("cache-only", "generate"), default="generate")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan-digest")
    parser.add_argument("--authorization-stdin", action="store_true")
    args = parser.parse_args()
    if args.apply != bool(args.plan_digest) or args.apply != args.authorization_stdin:
        parser.error("apply requires --plan-digest and --authorization-stdin; preview omits all three")
    from app.services.rardar_material_correction import apply_once, preview

    if args.apply:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            parser.error("authorization input too large")
        try:
            grant = json.loads(raw)
        except (UnicodeDecodeError, ValueError):
            parser.error("authorization input is not JSON")
        result = asyncio.run(
            apply_once(args.repository, mode=args.mode, expected_plan_digest=args.plan_digest, operator_grant=grant)
        )
    else:
        result = asyncio.run(preview(args.repository, mode=args.mode))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
