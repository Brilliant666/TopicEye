"""Run one explicitly authorized, paid Rardar material correction work slice."""

import argparse
import asyncio
import json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        required=True,
        choices=[
            "albert-weasker/niubigeo",
            "anthropics/financial-services",
            "craterserpentglow/discord-server-raider",
        ],
    )
    parser.add_argument("--apply", action="store_true", help="dispatch one bounded work slice")
    args = parser.parse_args()
    if not args.apply:
        parser.error("this command requires explicit --apply")
    from app.services.rardar_material_correction import apply_once

    print(json.dumps(asyncio.run(apply_once(args.repository)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
