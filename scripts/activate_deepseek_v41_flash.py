#!/usr/bin/env python3
"""Activate DeepSeek V4.1 Flash in the API Gateway (中转站).

DeepSeek released V4.1 Flash on 2026-09-10 under the official API model name
``deepseek-flash``. The Gateway resolves models from *database* records, so
editing ``config/gateway/providers.yaml`` alone does not make the model
callable. This script performs the repeatable database half of the upgrade:

1. bootstrap the configured provider/model catalog (idempotent upsert),
2. sync provider metadata, which records a new *pending* price revision when
   the reviewed catalog price differs from the active one,
3. optionally approve pending DeepSeek revisions so the model can be routed.

Safety properties:

* Re-running is harmless: bootstrapping upserts by ``public_id`` and price
  revisions are deduplicated by a content hash.
* Only DeepSeek revisions are ever approved, and only when ``--approve`` is
  passed. Other providers' pending revisions are left untouched.
* Existing live prices and historical request logs are never rewritten. A
  previous active revision is marked ``superseded`` by the existing approval
  code path, which keeps the billing audit trail intact.

Usage
-----
    python -m scripts.activate_deepseek_v41_flash --dry-run
    python -m scripts.activate_deepseek_v41_flash --approve --approved-by <admin-user-id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.config import get_settings  # noqa: E402
from packages.database.models import (  # noqa: E402
    GatewayModel,
    GatewayPriceRevision,
    GatewayProvider,
)
from packages.database.session import SessionLocal  # noqa: E402
from packages.gateway.catalog import provider_catalog  # noqa: E402
from packages.gateway.metadata import (  # noqa: E402
    approve_price_revision,
    bootstrap_gateway_catalog,
    sync_provider_metadata,
)

TARGET_PROVIDER = "deepseek"


def _catalog_models() -> list[str]:
    catalog = provider_catalog(TARGET_PROVIDER)
    return [str(item.get("public_id")) for item in (catalog.get("models") or []) if item.get("public_id")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate DeepSeek V4.1 Flash in the API Gateway")
    parser.add_argument("--approve", action="store_true", help="approve pending DeepSeek price revisions")
    parser.add_argument("--approved-by", default="", help="admin user id recorded on the approval")
    parser.add_argument("--dry-run", action="store_true", help="report state without writing or approving")
    args = parser.parse_args()

    settings = get_settings()
    wanted = _catalog_models()
    print(f"catalog path: {settings.gateway_catalog_path}")
    print(f"catalog DeepSeek models: {', '.join(wanted) or '(none)'}")
    print(f"gateway enabled: {settings.gateway_enabled}")
    print(f"enabled providers: {', '.join(settings.gateway_enabled_providers)}")

    if args.approve and not args.approved_by:
        print("ERROR: --approve requires --approved-by <admin user id> for the audit record", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        existing = {row.public_id: row for row in db.query(GatewayModel).all()}
        print("\n--- before ---")
        for public_id in wanted:
            row = existing.get(public_id)
            if row is None:
                print(f"  {public_id}: ABSENT")
            else:
                print(
                    f"  {public_id}: provider_model_id={row.provider_model_id} "
                    f"status={row.status} active_price={'yes' if row.active_pricing_id else 'no'}"
                )

        if args.dry_run:
            print("\ndry run: no changes written")
            return 0

        created = bootstrap_gateway_catalog(db)
        print(f"\nbootstrap: providers_added={created['providers']} models_added={created['models']}")

        providers = {row.name: row for row in db.query(GatewayProvider).all()}
        provider = providers.get(TARGET_PROVIDER)
        if provider is None:
            print(f"ERROR: provider '{TARGET_PROVIDER}' is not configured (check GATEWAY_ENABLED_PROVIDERS)", file=sys.stderr)
            return 1
        if not provider.enabled:
            print(f"ERROR: provider '{TARGET_PROVIDER}' is disabled; set GATEWAY_ENABLED_PROVIDERS to include it", file=sys.stderr)
            return 1

        sync = sync_provider_metadata(db, TARGET_PROVIDER, triggered_by="deepseek-v41-flash-activation")
        print(f"sync: status={sync.status} models_seen={sync.models_seen} prices_seen={sync.prices_seen}")

        model_ids = [row.id for row in db.query(GatewayModel).filter(GatewayModel.provider_id == provider.id).all()]
        pending = (
            db.query(GatewayPriceRevision)
            .filter(
                GatewayPriceRevision.model_id.in_(model_ids),
                GatewayPriceRevision.status == "pending",
            )
            .order_by(GatewayPriceRevision.synced_at.asc())
            .all()
        )
        print(f"pending DeepSeek price revisions: {len(pending)}")

        if not args.approve:
            for revision in pending:
                model = db.get(GatewayModel, revision.model_id)
                print(
                    f"  PENDING {model.public_id if model else revision.model_id} "
                    f"revision={revision.id} official={revision.official_prices_json} "
                    f"final={revision.final_prices_json}"
                )
            print("\nno approval requested; re-run with --approve --approved-by <admin id> to activate routing")
            return 0

        for revision in pending:
            model = db.get(GatewayModel, revision.model_id)
            approve_price_revision(db, revision.id, args.approved_by)
            print(f"  APPROVED {model.public_id if model else revision.model_id} revision={revision.id}")

        print("\n--- after ---")
        for public_id in wanted:
            row = db.query(GatewayModel).filter_by(public_id=public_id).one_or_none()
            if row is None:
                print(f"  {public_id}: ABSENT")
                continue
            revision = db.get(GatewayPriceRevision, row.active_pricing_id) if row.active_pricing_id else None
            print(
                f"  {public_id}: provider_model_id={row.provider_model_id} status={row.status} "
                f"active_price={'yes' if revision else 'no'}"
                + (f" final={revision.final_prices_json}" if revision else "")
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
