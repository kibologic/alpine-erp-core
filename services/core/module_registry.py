"""
Alpine ERP — Backend Module Registry

Modules self-register by calling register_module() on import.
main.py calls load_all_modules(app) during startup.
Enterprise modules register themselves by being imported in main.py.
"""
from typing import Callable
from fastapi import FastAPI

_registered_modules: list[dict] = []


def register_module(
    name: str,
    router_factory: Callable[[FastAPI], None],
    version: str = "1.0.0",
    tier: str = "core",  # "core" | "enterprise"
) -> None:
    _registered_modules.append({
        "name": name,
        "router_factory": router_factory,
        "version": version,
        "tier": tier,
    })


def load_all_modules(app: FastAPI) -> None:
    for module in _registered_modules:
        module["router_factory"](app)


def get_registered_modules() -> list[dict]:
    return [
        {"name": m["name"], "version": m["version"], "tier": m["tier"]}
        for m in _registered_modules
    ]
