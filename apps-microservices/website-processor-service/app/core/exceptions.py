class BatchProcessingError(Exception):
    """
    Raised when a batch processing operation fails.
    Carries the payloads of the *other* messages in the batch that were already ACKed
    so they can be manually sent to the DLQ.
    """
    def __init__(self, message: str, previous_payloads: list[dict], original_error: Exception = None):
        super().__init__(message)
        self.previous_payloads = previous_payloads
        self.original_error = original_error