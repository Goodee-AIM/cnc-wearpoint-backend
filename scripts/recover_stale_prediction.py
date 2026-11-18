"""Operator-only stale prediction inspection/recovery. No automatic scheduling.

From repository root:
  python -m scripts.recover_stale_prediction --measurement-id 123
  python -m scripts.recover_stale_prediction --measurement-id 123 --apply --confirm-workers-checked

Never run --apply before verifying the target job and database state.
"""

import argparse
import json

from app.services.prediction_execution import (
    inspect_prediction_claim,
    recover_stale_prediction,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurement-id", type=int, required=True)
    parser.add_argument("--min-age-minutes", type=int, default=30)
    parser.add_argument("--apply", action="store_true", help="Write failed status if safe")
    parser.add_argument(
        "--confirm-workers-checked", action="store_true",
        help="Confirm relevant active requests/workers have been investigated",
    )
    args = parser.parse_args()
    if args.measurement_id <= 0:
        parser.error("--measurement-id must be positive")
    if args.min_age_minutes < 30:
        parser.error("--min-age-minutes must be at least 30")
    if args.apply and not args.confirm_workers_checked:
        parser.error("--apply requires --confirm-workers-checked")
    if args.apply:
        result = recover_stale_prediction(args.measurement_id, args.min_age_minutes)
    else:
        result = inspect_prediction_claim(args.measurement_id, args.min_age_minutes)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
