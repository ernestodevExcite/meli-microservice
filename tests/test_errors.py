"""Tests unitarios de clasificacion de errores MELI (patrones de la guia)."""
from __future__ import annotations

from app.meli.errors import (
    MeliAuthError,
    MeliConflictError,
    MeliError,
    MeliForbiddenError,
    MeliNotFoundError,
    MeliQuotaError,
    MeliRateLimitError,
    MeliServerError,
    MeliUnprocessableError,
    MeliValidationError,
    classify_error,
    error_body,
    http_status_for,
    is_retryable,
)


def test_400_validation_error() -> None:
    err = classify_error(400, {"error": "validation_error", "message": "falta OPERATION"})
    assert isinstance(err, MeliValidationError)
    assert not is_retryable(err)


def test_400_not_available_quota_es_quota_no_validation() -> None:
    # Caso real visto en prod: 400 bad_request con mensaje 'Not available quota',
    # sin cause. Antes se mapeaba como MeliValidationError (confundia al CMS).
    err = classify_error(400, {"error": "bad_request", "message": "Not available quota", "cause": []})
    assert isinstance(err, MeliQuotaError)
    assert not isinstance(err, MeliValidationError)
    assert not is_retryable(err)
    assert http_status_for(err) == 402  # Payment Required


def test_400_quota_mensaje_en_espanol_tambien_mapea() -> None:
    err = classify_error(400, {"error": "validation_error", "message": "Limite de publicaciones alcanzado"})
    assert isinstance(err, MeliQuotaError)


def test_400_validation_con_cause_no_es_quota() -> None:
    # Si trae cause es un error de validacion real, no de cuota.
    err = classify_error(400, {
        "error": "validation_error",
        "message": "line break not allowed",
        "cause": [{"code": "line.break.not.allowed"}],
    })
    assert isinstance(err, MeliValidationError)
    assert not isinstance(err, MeliQuotaError)


def test_401_unauthorized() -> None:
    err = classify_error(401, {"error": "invalid_token", "message": "expired"})
    assert isinstance(err, MeliAuthError)
    assert is_retryable(err)


def test_403_forbidden() -> None:
    err = classify_error(403, {"error": "forbidden", "message": "scope insuficiente"})
    assert isinstance(err, MeliForbiddenError)
    assert http_status_for(err) == 403


def test_404_not_found() -> None:
    err = classify_error(404, {"error": "not_found", "message": "no existe ciudad"})
    assert isinstance(err, MeliNotFoundError)


def test_409_conflict_409_optimistic_locking() -> None:
    err = classify_error(409, {"error": "bad_request", "message": "optimistic locking error: conflict"})
    # El servidor MELI responde 'bad_request' con 409 a veces; no estamos basados
    # unicamente en error_code, tambien en status_code 409 -> Conflicto.
    assert isinstance(err, MeliConflictError)
    assert is_retryable(err)


def test_422_unprocessable() -> None:
    err = classify_error(422, {"error": "unprocessable_entity", "message": "algo negocio"})
    assert isinstance(err, MeliUnprocessableError)


def test_429_rate_limit() -> None:
    err = classify_error(429, {"error": "too_many_requests"})
    assert isinstance(err, MeliRateLimitError)
    assert is_retryable(err)


def test_500_server() -> None:
    err = classify_error(500, {"error": "internal_server_error"})
    assert isinstance(err, MeliServerError)
    assert is_retryable(err)
    assert http_status_for(err) == 502  # MELI 5xx -> Bad Gateway al CMS


def test_unknown_error_clasifica_base() -> None:
    err = classify_error(503, {"error": "service_unavailable"})
    assert isinstance(err, MeliError)


def test_http_status_for_cubre_todas_las_subclases() -> None:
    err = MeliValidationError(400, "x", body={"error": "validation_error"})
    assert http_status_for(err) == 400


def test_error_body_estructura_estandar() -> None:
    err = MeliQuotaError(400, "Not available quota", cause=[], body={"error": "bad_request", "message": "Not available quota"})
    body = error_body(err)
    assert body["error"] == "meli_api_error"
    assert body["meli_status"] == 400
    assert body["meli_error_code"] == "bad_request"
    assert body["message"] == "Not available quota"
    assert body["cause"] == []
