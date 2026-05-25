"""Thin composition entry point. The work happens in `fh6.composition`."""

from __future__ import annotations

from fastapi import FastAPI

from fh6.composition.application import build_application
from fh6.composition.infrastructure import build_infrastructure
from fh6.composition.interfaces import assemble_app
from fh6.infrastructure.config import AppConfig, load_from_env
from fh6.infrastructure.logging import configure_logging


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = load_from_env()
    configure_logging(level=config.log_level, fmt=config.log_format)
    infra = build_infrastructure(config)
    application = build_application(infra)
    return assemble_app(infra, application)
