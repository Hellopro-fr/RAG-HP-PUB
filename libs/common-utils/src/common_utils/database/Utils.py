class Utils:
    def sanitize_record(record: dict) -> dict:
        return {k: ("" if v is None else v) for k, v in record.items()}