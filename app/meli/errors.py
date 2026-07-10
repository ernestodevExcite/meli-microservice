"""Excepciones y mapa de errores MELI conocidos.

Baseline con los errores documentados en la Guia API Inmuebles MELI.
"""
from __future__ import annotations


class MeliError(Exception):
    """Error base de la API MELI."""

    def __init__(self, status_code: int, message: str, *, cause: list | None = None, body: dict | None = None) -> None:
        self.status_code = status_code
        self.message = message
        self.cause = cause or []
        self.body = body or {}
        super().__init__(f"{status_code} {message}")


class MeliValidationError(MeliError):
    """400 validation_error: atributos obligatorios ausentes o JSON invalido."""


class MeliAuthError(MeliError):
    """401 unauthorized: token invalido/expirado."""


class MeliForbiddenError(MeliError):
    """403 forbidden: scopes insuficientes, IP bloqueada, official_store_id, etc."""


class MeliNotFoundError(MeliError):
    """404 not_found: item/usuario/ciudad no existe."""


class MeliConflictError(MeliError):
    """409 optimistic_locking: MELI aun no termino de procesar el item. Retry."""


class MeliUnprocessableError(MeliError):
    """422 unprocessable_entity: reglas de negocio del vertical inmuebles."""


class MeliRateLimitError(MeliError):
    """429 too_many_requests. Backoff exponencial."""


class MeliServerError(MeliError):
    """500 internal_server_error. Retry."""


# Errores conocidos de la guia -> mapeo a clase/tipo.
# Clave primaria: status_code. Secundaria (si existe): error_code de MELI.
KNOWN_ERRORS: dict[int, dict[str, type[MeliError]]] = {
    400: {
        "validation_error": MeliValidationError,
        "bad_request": MeliValidationError,
    },
    401: {
        "unauthorized": MeliAuthError,
        "invalid_token": MeliAuthError,
        "invalid_grant": MeliAuthError,
    },
    403: {
        "forbidden": MeliForbiddenError,
    },
    404: {
        "not_found": MeliNotFoundError,
    },
    409: {
        "conflict": MeliConflictError,
        "bad_request": MeliConflictError,  # MELI responde bad_request en 409 (optimistic locking)
        "item.optimistic_locking_error": MeliConflictError,
    },
    422: {
        "unprocessable_entity": MeliUnprocessableError,
    },
    429: {
        "too_many_requests": MeliRateLimitError,
    },
    500: {
        "internal_server_error": MeliServerError,
    },
}

# Status codes que siempre mapean a una clase especifica, sin importar error_code.
DEFAULT_BY_STATUS: dict[int, type[MeliError]] = {
    400: MeliValidationError,
    401: MeliAuthError,
    403: MeliForbiddenError,
    404: MeliNotFoundError,
    409: MeliConflictError,
    422: MeliUnprocessableError,
    429: MeliRateLimitError,
}


def classify_error(status_code: int, body: dict) -> MeliError:
    error_code = (body.get("error") or "").lower()
    message = body.get("message", "")
    cause = body.get("cause") or []

    cls: type[MeliError] | None = None
    by_status = KNOWN_ERRORS.get(status_code)
    if by_status:
        cls = by_status.get(error_code)
    if cls is None and status_code in DEFAULT_BY_STATUS:
        cls = DEFAULT_BY_STATUS[status_code]
    if cls is None:
        cls = MeliServerError if status_code >= 500 else MeliError

    return cls(status_code, message, cause=cause, body=body)


def is_retryable(err: MeliError) -> bool:
    """Define que status codes disparan reintentos automaticos."""
    return isinstance(err, (MeliConflictError, MeliRateLimitError, MeliServerError, MeliAuthError))
