"""Standardized DTO envelope helpers for API responses."""

from typing import Any, Dict, Optional

from flask import jsonify


def success_response(
    data: Any = None,
    message: str = "OK",
    status: int = 200,
    meta: Optional[Dict[str, Any]] = None,
):
    payload: Dict[str, Any] = {
        "success": True,
        "message": message,
        "data": data,
    }
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def error_response(
    code: str,
    message: str,
    status: int = 400,
    details: Any = None,
):
    error: Dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details is not None:
        error["details"] = details

    payload: Dict[str, Any] = {
        "success": False,
        "message": message,
        "error": error,
    }
    return jsonify(payload), status

