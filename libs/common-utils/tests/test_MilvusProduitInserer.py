"""Regression guard for the correspondance ``id_produit_milvus`` field size.

``id_produit_milvus`` stores the comma-joined list of a product's Milvus chunk
primary keys. It is read and ``explode(",")``-parsed by the BO cleanup job
(``nettoyage_produits_supprimes_milvus.php``) to delete those vectors from
``produits_3``, so it MUST be able to hold every PK — silently truncating it
would orphan vectors on product removal.

The original ``VARCHAR(512)`` overflowed at ~28 chunks (Milvus error code 1100,
observed 607 chars for a 32-chunk product). This test pins the field limit high
enough that realistic products always fit, and within the Milvus VARCHAR ceiling.
"""

from common_utils.database.MilvusProduitInserer import ID_PRODUIT_MILVUS_MAX_LENGTH

# A Milvus auto-id PK is an 18-digit int; joined with a comma => ~19 chars/PK.
_CHARS_PER_PK = 19
# Products can chunk into hundreds of pieces; keep generous headroom.
_MIN_SUPPORTED_CHUNKS = 1000
# The 32-chunk product whose 607-char blob triggered the original overflow.
_OBSERVED_FAILURE_CHARS = 607
# Milvus hard ceiling for a VARCHAR field.
_MILVUS_VARCHAR_MAX = 65535


def test_id_produit_milvus_holds_many_chunk_pks():
    assert ID_PRODUIT_MILVUS_MAX_LENGTH >= _MIN_SUPPORTED_CHUNKS * _CHARS_PER_PK
    # Must comfortably exceed the original 512 limit and the observed overflow.
    assert ID_PRODUIT_MILVUS_MAX_LENGTH > _OBSERVED_FAILURE_CHARS
    # Must stay within the Milvus VARCHAR ceiling.
    assert ID_PRODUIT_MILVUS_MAX_LENGTH <= _MILVUS_VARCHAR_MAX
