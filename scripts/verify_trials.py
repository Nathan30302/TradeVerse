#!/usr/bin/env python3
"""
Verify / optionally repair Pro Plus trial clocks.

Usage (from repo root):
  python3 scripts/verify_trials.py
  python3 scripts/verify_trials.py --repair

Prints counts and sample end-date / days-left calculations using the same
helpers as the sidebar and billing UI.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

# Repo root on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Run ensure_user_pro_plus_trial for every user and commit changes",
    )
    args = parser.parse_args()

    os.environ.setdefault("TV_ALL_USERS_PROPLUS_TRIAL", "1")
    os.environ.setdefault("TV_ALL_USERS_PROPLUS_TRIAL_DAYS", "60")
    os.environ.setdefault("TV_TRIAL_DAYS_PRO_PLUS", "60")

    from app import create_app, db
    from app.models.user import User
    from app.services.entitlements import (
        ensure_user_pro_plus_trial,
        get_personal_trial_end,
        get_trial_days_remaining,
        get_effective_subscription_state,
        trial_period_days,
    )

    app = create_app()
    now = datetime.now(timezone.utc)
    with app.app_context():
        users = User.query.order_by(User.id).all()
        print(f"now_utc={now.isoformat()}")
        print(f"trial_period_days={trial_period_days()}")
        print(f"users={len(users)}")

        with_end = 0
        future_end = 0
        past_end = 0
        repaired = 0
        samples = []

        for u in users:
            if args.repair and ensure_user_pro_plus_trial(u):
                repaired += 1

            end = get_personal_trial_end(u)
            left = get_trial_days_remaining(u)
            st = get_effective_subscription_state(u)
            raw = getattr(u, "trial_ends_at", None)
            if raw is not None:
                with_end += 1
            if end is not None:
                end_aware = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
                if end_aware >= now:
                    future_end += 1
                else:
                    past_end += 1

            if len(samples) < 12:
                samples.append(
                    {
                        "id": u.id,
                        "username": u.username,
                        "created_at": u.created_at,
                        "trial_ends_at": raw,
                        "display_end": end,
                        "days_left": left,
                        "effective": f"{st.tier}/{st.status}",
                    }
                )

        if args.repair and repaired:
            db.session.commit()

        print(f"with_trial_ends_at={with_end}")
        print(f"display_end_in_future={future_end}")
        print(f"display_end_in_past={past_end}")
        if args.repair:
            print(f"repaired={repaired}")

        print("\nSamples (same source of truth as chip / billing):")
        for s in samples:
            print(
                f"  id={s['id']} {s['username']!r} effective={s['effective']} "
                f"days_left={s['days_left']} display_end={s['display_end']} "
                f"db_trial_ends_at={s['trial_ends_at']} created_at={s['created_at']}"
            )

        # Consistency check: days_left and display_end must agree when trialing.
        bad = 0
        for u in users:
            st = get_effective_subscription_state(u)
            if st.status != "trialing":
                continue
            end = get_personal_trial_end(u) or st.trial_ends_at
            left = get_trial_days_remaining(u)
            if end is None or left is None:
                continue
            end_aware = end if getattr(end, "tzinfo", None) else end.replace(tzinfo=timezone.utc)
            if left == 0 and end_aware > now:
                bad += 1
                print(f"INCONSISTENT: user {u.id} days_left=0 but end={end_aware}")
            if left and left > 0 and end_aware < now:
                bad += 1
                print(f"INCONSISTENT: user {u.id} days_left={left} but end in past {end_aware}")

        if bad:
            print(f"\nFAIL: {bad} inconsistent trial display row(s)")
            return 1
        print("\nOK: trial end date and days left are consistent for trialing users")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
