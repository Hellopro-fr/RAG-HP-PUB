class ServiceError(Exception):
    code = "INTERNAL"


class NotFound(ServiceError):
    code = "NOT_FOUND"


class AlreadyExists(ServiceError):
    code = "ALREADY_EXISTS"


class InvalidArgument(ServiceError):
    code = "INVALID_ARGUMENT"


class FailedPrecondition(ServiceError):
    code = "FAILED_PRECONDITION"
