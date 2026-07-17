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


class MeliQuotaError(MeliError):
    """400 bad_request con mensaje 'Not available quota': cupo del paquete agotado.

    No es un error de validacion (el payload es correcto); el vendedor necesita
    adquirir mas cuota o cambiar de paquete. No hay retry posible.
    """


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


# Substrings en el mensaje MELI (insensitive) que indican cuota agotada
# aunque venga como 400 bad_request. MELI no siempre usa un error_code dedicado.
_QUOTA_MESSAGES = (
    "not available quota",
    "quota exceeded",
    "pack_quota_exceeded",
    "no disponible cuota",
    "limite de publicaciones",
)


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


def _looks_like_quota(message: str) -> bool:
    msg = (message or "").lower()
    return any(s in msg for s in _QUOTA_MESSAGES)


def classify_error(status_code: int, body: dict) -> MeliError:
    error_code = (body.get("error") or "").lower()
    message = body.get("message", "") or ""
    cause = body.get("cause") or []

    # Caso especial: 400 con mensaje de cuota -> no es validacion, es quota.
    # MELI usa 'bad_request'/'validation_error' como error_code indistintamente.
    if status_code == 400 and _looks_like_quota(message) and not cause:
        return MeliQuotaError(status_code, message, cause=cause, body=body)

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


# ───── Mapeo MELI -> HTTP para el router del microservicio ─────
# Cada subclase de MeliError se traduce a un status HTTP " honesto":
#   - 4xx de negocio MELI se conserva como 4xx (no se enmascara como 502).
#   - 5xx de MELI se expone como 502 (Bad Gateway): fallo del upstream.
#   - Errores transitorios retryados que llegan aca son "definitivos" (se agoto retry).
# El detalle (cause, message, error_code) se propaga en el body de la respuesta.
MELI_TO_HTTP_STATUS: dict[type[MeliError], int] = {
    MeliValidationError: 400,
    MeliQuotaError: 402,  # Payment Required: el vendedor necesita mas cuota
    MeliAuthError: 401,
    MeliForbiddenError: 403,
    MeliNotFoundError: 404,
    MeliConflictError: 409,
    MeliUnprocessableError: 422,
    MeliRateLimitError: 429,
    MeliServerError: 502,
}


def http_status_for(err: MeliError) -> int:
    """Status HTTP que el microservicio debe devolver al CMS segun tipo de error MELI."""
    for cls, http_status in MELI_TO_HTTP_STATUS.items():
        if isinstance(err, cls):
            return http_status
    # MeliError generico (no subclassificado): 502 si 5xx, 400 si 4xx, 502 default.
    return 502 if err.status_code >= 500 else 400


def error_body(err: MeliError) -> dict:
    """Estructura estandar del body de error devuelto al CMS."""
    return {
        "error": "meli_api_error",
        "meli_status": err.status_code,
        "meli_error_code": (err.body.get("error") if isinstance(err.body, dict) else None),
        "message": err.message,
        "cause": err.cause,
    }
