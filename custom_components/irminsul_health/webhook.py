"""Webhook handling for Irminsul Health."""

from __future__ import annotations

import hmac
import json
from http import HTTPStatus
from typing import Any

from aiohttp import web
from aiohttp.web import Request, Response
from homeassistant.core import HomeAssistant

from .const import (
    EVENT_OBSERVATION_RECEIVED,
    MAX_REQUEST_BYTES,
)
from .models import (
    IrminsulRuntimeData,
    Observation,
    ObservationValidationError,
    parse_observation,
)
from .storage import ObservationConflictError

MAX_BATCH_SIZE = 100


async def async_handle_webhook(
    hass: HomeAssistant,
    runtime_data: IrminsulRuntimeData,
    subject_id: str,
    ingest_token: str,
    request: Request,
) -> Response:
    """Receive a versioned observation batch."""
    authorization = request.headers.get("Authorization", "")
    if not hmac.compare_digest(authorization, f"Bearer {ingest_token}"):
        return web.json_response(
            {"error": "unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    retry_after = runtime_data.rate_limiter.consume(hass.loop.time())
    if retry_after is not None:
        return web.json_response(
            {"error": "rate limit exceeded"},
            status=HTTPStatus.TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
        )

    if (
        request.content_length is not None
        and request.content_length > MAX_REQUEST_BYTES
    ):
        return _error("request is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

    try:
        body = await request.content.read(MAX_REQUEST_BYTES + 1)
        if len(body) > MAX_REQUEST_BYTES:
            return _error("request is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        payload: Any = json.loads(body)
    except (json.JSONDecodeError, RecursionError, UnicodeDecodeError):
        return _error("body must be valid JSON", HTTPStatus.BAD_REQUEST)

    if not isinstance(payload, dict):
        return _error("body must be an object", HTTPStatus.BAD_REQUEST)
    if payload.get("schema_version") != 1:
        return _error("schema_version must be 1", HTTPStatus.BAD_REQUEST)

    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list) or not raw_observations:
        return _error("observations must be a non-empty array", HTTPStatus.BAD_REQUEST)
    if len(raw_observations) > MAX_BATCH_SIZE:
        return _error(
            f"a batch can contain at most {MAX_BATCH_SIZE} observations",
            HTTPStatus.BAD_REQUEST,
        )

    observations: list[Observation] = []
    try:
        for item in raw_observations:
            observations.append(parse_observation(item))
    except ObservationValidationError as err:
        return _error(str(err), HTTPStatus.BAD_REQUEST)

    try:
        accepted, duplicates = await runtime_data.store.async_add_many(observations)
    except ObservationConflictError as err:
        return _error(str(err), HTTPStatus.CONFLICT)
    if accepted:
        runtime_data.notify()
        hass.bus.async_fire(
            EVENT_OBSERVATION_RECEIVED,
            {
                "subject_id": subject_id,
                "metrics": sorted({item.metric for item in observations}),
                "accepted": accepted,
            },
        )

    return web.json_response({"accepted": accepted, "duplicates": duplicates})


def _error(message: str, status: HTTPStatus) -> Response:
    return web.json_response({"error": message}, status=status)
