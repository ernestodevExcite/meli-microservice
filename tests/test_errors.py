"""Tests unitarios de clasificacion de errores MELI (patrones de la guia)."""
from __future__ import annotations

from app.meli.errors import (
    MeliAuthError,
    MeliConflictError,
    MeliError,
    MeliNotFoundError,
    MeliRateLimitError,
    MeliServerError,
    MeliUnprocessableError,
    MeliValidationError,
    classify_error,
    is_retryable,
)


def test_400_validation_error() -> None:
    err = classify_error(400, {"error": "validation_error", "message": "falta OPERATION"})
    assert isinstance(err, MeliValidationError)
    assert not is_retryable(err)


def test_401_unauthorized() -> None:
    err = classify_error(401, {"error": "invalid_token", "message": "expired"})
    assert isinstance(err, MeliAuthError)
    assert is_retryable(err)


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


def test_unknown_error_clasifica_base() -> None:
    err = classify_error(503, {"error": "service_unavailable"})
    assert isinstance(err, MeliError)
