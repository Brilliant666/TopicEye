"""Compatibility read-only preview for evidence-bound cache reassembly.

Apply moved to the operator-granted correct_rardar_material_once command.
"""

import argparse
import asyncio
import json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    from app.services.rardar_material_correction import preview

    result = asyncio.run(preview(args.repository, mode="cache-only"))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
