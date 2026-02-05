import sys
import os

# Add the service root to path to verify imports works as if running from app root or similar
service_root = (
    "/home/sandratra/RAG-HP-PUB/apps-microservices/graph-rag-normalize-unite-service"
)
sys.path.append(service_root)

from infrastructure.unit_normalization_service import unit_normalizer


def test_normalization():
    value = 40.0
    unit = "dB(A)"
    label = "Niveau pression acoustique"

    print(f"Testing normalization for: value={value}, unit='{unit}', label='{label}'")

    result = unit_normalizer.normalize(label, unit, value)

    print(f"Result: {result}")

    if (
        result
        and result.get("valeur_canonique") == 40.0
        and result.get("unite_canonique") == "decibel"
    ):
        print("SUCCESS: Normalization worked correctly.")
        return True
    else:
        print("FAILURE: Normalization failed or returned incorrect result.")
        return False


if __name__ == "__main__":
    success = test_normalization()
    if not success:
        sys.exit(1)
