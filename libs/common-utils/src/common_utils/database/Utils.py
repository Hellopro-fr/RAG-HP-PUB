class Utils:
    # Control chars that are safe to keep (tab, newline, carriage return).
    _KEEP_CTRL = "\t\n\r"

    @staticmethod
    def to_valid_utf8(text: str) -> str:
        """Drop lone surrogates and C0/C1 control chars (keeping tab/newline/CR)
        so the string always encodes to valid UTF-8 on the Milvus wire.

        Milvus rejects any string field containing invalid UTF-8 (code 65535);
        lone surrogates (\\ud800-\\udfff) are the usual culprit, coming from an
        upstream errors='surrogateescape' decode of a non-UTF-8 filename.
        """
        return "".join(
            ch
            for ch in text
            if not ("\ud800" <= ch <= "\udfff")
            and (ord(ch) >= 32 or ch in Utils._KEEP_CTRL)
        )

    @staticmethod
    def _sanitize_value(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return Utils.to_valid_utf8(value)
        return value

    @staticmethod
    def sanitize_record(record: dict) -> dict:
        return {k: Utils._sanitize_value(v) for k, v in record.items()}
