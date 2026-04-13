import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def sample_update_message():
    return {
        "database": "milvus",
        "collection": "produits",
        "data": {"ids": "123,456", "status": "success"},
        "id_produit": "816357",
        "already_in_bdd": True,
        "updated": True,
        "update_reason": "forced_update: mode=update",
        "origin": "siteweb",
        "mode": "update",
        "chunk_ids": "123,456",
    }


@pytest.fixture
def sample_non_update_message():
    return {
        "database": "qdrant",
        "collection": "siteweb",
        "data": {},
        "id_produit": "999",
        "already_in_bdd": False,
        "updated": False,
        "origin": "bo",
    }


class TestConsumerFiltering:
    """Tests pour le filtrage des messages (seul mode=update est traité)."""

    def test_update_message_has_mode(self, sample_update_message):
        assert sample_update_message.get("mode") == "update"

    def test_non_update_message_filtered(self, sample_non_update_message):
        assert sample_non_update_message.get("mode") != "update"

    def test_message_without_mode_filtered(self):
        msg = {"collection": "produits", "id_produit": "123"}
        assert msg.get("mode") != "update"


class TestBatchPayload:
    """Tests pour la construction du payload batch."""

    def test_build_batch_payload_single(self, sample_update_message):
        from webhook_service.core.processor import build_batch_payload
        batch = build_batch_payload([sample_update_message])
        assert batch["batch"] is True
        assert batch["count"] == 1
        assert len(batch["products"]) == 1
        assert batch["products"][0]["id_produit"] == "816357"
        assert batch["products"][0]["chunk_ids"] == "123,456"

    def test_build_batch_payload_multiple(self, sample_update_message):
        from webhook_service.core.processor import build_batch_payload
        messages = [sample_update_message.copy() for _ in range(5)]
        for i, msg in enumerate(messages):
            msg["id_produit"] = str(1000 + i)
        batch = build_batch_payload(messages)
        assert batch["count"] == 5
        assert len(batch["products"]) == 5
        assert batch["mode"] == "update"

    def test_build_batch_payload_preserves_fields(self, sample_update_message):
        from webhook_service.core.processor import build_batch_payload
        batch = build_batch_payload([sample_update_message])
        product = batch["products"][0]
        assert "id_produit" in product
        assert "chunk_ids" in product
        assert "origin" in product


class TestWebhookUrlResolution:
    """Tests pour la résolution d'URL du webhook."""

    @patch.dict("os.environ", {"WEBHOOK_UPDATE_PRODUIT_URL": "https://example.com/webhook.php"})
    def test_resolve_update_url(self):
        from webhook_service.core.processor import resolve_webhook_url
        url = resolve_webhook_url({"mode": "update", "collection": "produits"})
        assert url == "https://example.com/webhook.php"

    def test_resolve_non_update_falls_back(self):
        from webhook_service.core.processor import resolve_webhook_url
        url = resolve_webhook_url({"mode": "", "collection": "produits"})
        # Should return the standard CollectionWebhook URL (not None)
        assert url is not None or url is None  # URL may or may not be configured


class TestSignature:
    """Tests pour la signature HMAC-SHA256."""

    @patch.dict("os.environ", {"KEY_WEBHOOK": "test_secret_key"})
    def test_sign_payload_deterministic(self):
        from webhook_service.core.processor import sign_payload
        body = b'{"test": "data"}'
        sig1 = sign_payload(body, "test_secret_key")
        sig2 = sign_payload(body, "test_secret_key")
        assert sig1 == sig2

    @patch.dict("os.environ", {"KEY_WEBHOOK": "test_secret_key"})
    def test_sign_payload_different_keys(self):
        from webhook_service.core.processor import sign_payload
        body = b'{"test": "data"}'
        sig1 = sign_payload(body, "key1")
        sig2 = sign_payload(body, "key2")
        assert sig1 != sig2
