"""Preview or apply a bounded, zero-outbound Profile cache correction."""

import argparse
import asyncio
import json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, choices=["zai-org/zcode", "hydra-db/hydradb"])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan-digest")
    args = parser.parse_args()
    if args.apply != bool(args.plan_digest):
        parser.error("--apply requires --plan-digest; preview must omit both")
    from app.services.rardar_cache_reassembly import apply, preview

    result = (
        asyncio.run(apply(args.repository, args.plan_digest))
        if args.apply
        else asyncio.run(preview(args.repository))[0]
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
