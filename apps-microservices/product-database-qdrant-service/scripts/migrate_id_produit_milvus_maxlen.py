#!/usr/bin/env python3
"""One-off migration: raise ``id_produit_milvus`` VARCHAR max_length on the
``correspondance_produits_bo_milvus_3`` Milvus/Zilliz collection 512 -> 65535.

WHY
    ``id_produit_milvus`` stores the comma-joined list of a product's chunk PKs.
    Products chunking into >=28 pieces overflow VARCHAR(512) (Milvus code 1100:
    "length of varchar field id_produit_milvus exceeds max length"), which fails
    the correspondance insert and thus the whole product insert/update. The field
    is read+parsed by the BO cleanup job (nettoyage_produits_supprimes_milvus.php)
    to delete those vectors, so it must hold the FULL list -- enlarge, not truncate.

    Milvus docs: changing a VarChar max_length is a lightweight operation that
    only updates validation criteria for new data and does NOT reorganize data.
    Requires Milvus/Zilliz >= 2.5. Existing rows are untouched.

IDEMPOTENT
    Re-running is safe: if the field is already >= target, it is a no-op.

RUN (inside a container that has common_utils + the ZILLIZ_* env vars):
    docker exec -it <product-database-qdrant-service> \
        python scripts/migrate_id_produit_milvus_maxlen.py

    # verify the parsing logic without touching any server:
    python scripts/migrate_id_produit_milvus_maxlen.py --selfcheck

Optional endpoint overrides (if the host:port form below is not reachable):
    ZILLIZ_MILVUS_URI   full client uri, e.g. https://in03-xxxx.zillizcloud.com
    ZILLIZ_MILVUS_TOKEN full token, e.g. "user:password" or an API key
"""

import logging
import os
import sys
from typing import Any, Dict, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("migrate_id_produit_milvus_maxlen")

COLLECTION = "correspondance_produits_bo_milvus_3"
FIELD = "id_produit_milvus"
NEW_MAX_LENGTH = 65535


def extract_max_length(describe: Dict[str, Any], field_name: str) -> Optional[int]:
    """Pull a VARCHAR field's max_length out of a describe_collection() result.

    Pure/server-free so it can be unit-checked. Returns None if the field or its
    max_length is absent (describe shapes vary across pymilvus versions).
    """
    for field in describe.get("fields", []):
        if field.get("name") != field_name:
            continue
        params = field.get("params") or {}
        max_length = params.get("max_length", field.get("max_length"))
        return int(max_length) if max_length is not None else None
    return None


def _build_client():
    from pymilvus import MilvusClient
    from common_utils.database.config.settings import settings

    uri = os.getenv("ZILLIZ_MILVUS_URI")
    if not uri:
        if not settings.ZILLIZ_URI:
            raise SystemExit("ZILLIZ_URI not set and ZILLIZ_MILVUS_URI missing.")
        uri = f"http://{settings.ZILLIZ_URI}:{settings.ZILLIZ_PORT}"
    token = os.getenv("ZILLIZ_MILVUS_TOKEN") or (
        f"{settings.ZILLIZ_USER}:{settings.ZILLIZ_PASSWORD}"
    )
    log.info("Connecting to Milvus at %s", uri)
    return MilvusClient(uri=uri, token=token)


def _selfcheck() -> int:
    """Server-free check of the describe-parsing logic."""
    desc_new = {"fields": [{"name": FIELD, "params": {"max_length": 65535}}]}
    desc_old = {"fields": [{"name": FIELD, "params": {"max_length": 512}}]}
    desc_flat = {"fields": [{"name": FIELD, "max_length": 512}]}  # alt shape
    desc_missing = {"fields": [{"name": "other", "params": {"max_length": 10}}]}
    assert extract_max_length(desc_new, FIELD) == 65535
    assert extract_max_length(desc_old, FIELD) == 512
    assert extract_max_length(desc_flat, FIELD) == 512
    assert extract_max_length(desc_missing, FIELD) is None
    # Idempotency decision: skip only when already >= target.
    assert not (512 >= NEW_MAX_LENGTH)
    assert 65535 >= NEW_MAX_LENGTH
    log.info("selfcheck OK")
    return 0


def main() -> int:
    if "--selfcheck" in sys.argv:
        return _selfcheck()

    client = _build_client()

    before = extract_max_length(client.describe_collection(COLLECTION), FIELD)
    log.info("Current %s.%s max_length = %s", COLLECTION, FIELD, before)
    if before is not None and before >= NEW_MAX_LENGTH:
        log.info("Already >= %s -- nothing to do (idempotent).", NEW_MAX_LENGTH)
        return 0

    log.info(
        "Altering %s.%s max_length %s -> %s ...",
        COLLECTION, FIELD, before, NEW_MAX_LENGTH,
    )
    client.alter_collection_field(
        collection_name=COLLECTION,
        field_name=FIELD,
        field_params={"max_length": NEW_MAX_LENGTH},
    )

    after = extract_max_length(client.describe_collection(COLLECTION), FIELD)
    if after is not None and after != NEW_MAX_LENGTH:
        log.error("Verification FAILED: max_length is %s, expected %s.", after, NEW_MAX_LENGTH)
        return 1
    log.info(
        "OK: %s.%s max_length is now %s%s.",
        COLLECTION, FIELD, after,
        "" if after is not None else " (verify manually: describe shape unread)",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
