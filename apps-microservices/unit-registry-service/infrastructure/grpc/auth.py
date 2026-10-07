"""Bearer check on write RPCs ([J] D10 + B.3). Reads and ValidateUnit stay open.
The authorization header is never logged."""
from __future__ import annotations

import hmac

import grpc

_SERVICE = "/unit_registry.UnitRegistryService/"
WRITE_METHODS = frozenset(_SERVICE + name for name in (
    "RegisterUnit", "UpdateUnit", "DeleteUnit",
    "CreateUnitType", "UpdateUnitType", "DeactivateUnitType", "SetDimensionTypes",
))


class AdminKeyInterceptor(grpc.ServerInterceptor):
    def __init__(self, admin_key: str):
        if not admin_key:
            raise ValueError("UNITS_ADMIN_KEY must be set")
        self._expected = f"Bearer {admin_key}".encode()

        def deny(request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing or invalid admin bearer")

        self._deny = grpc.unary_unary_rpc_method_handler(deny)

    def intercept_service(self, continuation, handler_call_details):
        if handler_call_details.method in WRITE_METHODS:
            metadata = dict(handler_call_details.invocation_metadata or ())
            supplied = metadata.get("authorization", "").encode()
            if not hmac.compare_digest(supplied, self._expected):
                return self._deny
        return continuation(handler_call_details)
