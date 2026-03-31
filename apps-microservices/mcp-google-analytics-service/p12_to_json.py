"""Convert a P12 service account key to ADC-compatible JSON format."""

import json
import os

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)


def convert_p12_to_json() -> None:
    p12_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS_P12", "/secrets/gcp-credentials.p12"
    )
    p12_password = os.environ.get("GOOGLE_P12_PASSWORD", "notasecret").encode()
    service_account_email = os.environ["GOOGLE_SERVICE_ACCOUNT_EMAIL"]
    project_id = os.environ.get("GOOGLE_PROJECT_ID", "")

    with open(p12_path, "rb") as f:
        private_key, _, _ = pkcs12.load_key_and_certificates(f.read(), p12_password)

    if private_key is None:
        raise ValueError("No private key found in P12 file")

    pem_bytes = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption(),
    )

    credentials = {
        "type": "service_account",
        "project_id": project_id,
        "private_key": pem_bytes.decode(),
        "client_email": service_account_email,
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    }

    output_path = "/tmp/gcp-credentials.json"
    with open(output_path, "w") as f:
        json.dump(credentials, f)


if __name__ == "__main__":
    convert_p12_to_json()