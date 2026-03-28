# plugin_loader.py
# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from __future__ import annotations

import importlib
import inspect
import logging
import types
from typing import Any, Callable, Dict, Tuple, TypedDict, cast

from pydantic import BaseModel
from log_setup import should_log_exception_trace

from alerts.base import BaseAlertPlugin

_PLUGIN_PACKAGE_BY_FAMILY: Dict[str, str] = {
    "alerts": "alerts.plugins",
    "bots": "bots.plugins",
    "lookup": "lookup.plugins",
}

# (family, name) -> imported module
_PLUGIN_MODULES: Dict[Tuple[str, str], types.ModuleType] = {}


class _AlertPluginRegistryEntry(TypedDict):
    module: types.ModuleType
    plugin_class: type[BaseAlertPlugin]


# alert name -> module + plugin class (only for family "alerts")
_ALERT_REGISTRY: Dict[str, _AlertPluginRegistryEntry] = {}


def _register_alert_module(plugin_name: str, module: types.ModuleType) -> None:
    logger = logging.getLogger("plugin_loader")
    plugin_classes: list[type[BaseAlertPlugin]] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, BaseAlertPlugin) and obj is not BaseAlertPlugin:
            plugin_classes.append(obj)

    if not plugin_classes:
        raise ValueError(f"alerts.plugins.{plugin_name} does not define a BaseAlertPlugin subclass.")
    if len(plugin_classes) > 1:
        names = ", ".join(c.__name__ for c in plugin_classes)
        raise ValueError(
            f"alerts.plugins.{plugin_name} defines multiple BaseAlertPlugin subclasses ({names}); "
            "keep one plugin class per plugin module."
        )

    _ALERT_REGISTRY[plugin_name] = {
        "module": module,
        "plugin_class": plugin_classes[0],
    }
    logger.debug(
        "Registered alert plugin module: %s (class %s)",
        plugin_name,
        plugin_classes[0].__name__,
    )


def ensure_plugin_loaded(family: str, name: str) -> types.ModuleType:
    """
    Import ``{package}.{name}`` for the given family and return the module.

    Families: ``alerts``, ``bots``, ``lookup`` -> ``alerts.plugins``, etc.
    Alert modules are also registered for :func:`get_plugin` / :func:`get_plugin_config_model`.
    """
    if family not in _PLUGIN_PACKAGE_BY_FAMILY:
        raise ValueError(f"Unknown plugin family {family!r}; expected one of {sorted(_PLUGIN_PACKAGE_BY_FAMILY)}.")

    key = (family, name)
    if key in _PLUGIN_MODULES:
        return _PLUGIN_MODULES[key]

    pkg = _PLUGIN_PACKAGE_BY_FAMILY[family]
    module = importlib.import_module(f"{pkg}.{name}")
    _PLUGIN_MODULES[key] = module

    if family == "alerts":
        _register_alert_module(name, module)

    return module


def load_plugins(family: str, names: list[str]) -> None:
    """Load every named plugin in a family (idempotent)."""
    logger = logging.getLogger("plugin_loader")
    for name in names:
        try:
            ensure_plugin_loaded(family, name)
        except Exception as e:
            logger.error(
                "Failed to load %s plugin %r: %s - %s",
                family,
                name,
                e.__class__.__name__,
                str(e),
                exc_info=should_log_exception_trace(),
            )
            raise


def get_plugin(plugin_name: str, plugin_config: BaseModel) -> BaseAlertPlugin:
    """
    Instantiate an alert plugin from a validated Pydantic config instance.
    Plugin modules must expose create_instance_plugin(config_model_instance).
    """
    ensure_plugin_loaded("alerts", plugin_name)

    entry = _ALERT_REGISTRY[plugin_name]
    module = entry["module"]

    factory_func = cast(
        Callable[[BaseModel], BaseAlertPlugin] | None,
        getattr(module, "create_instance_plugin", None),
    )
    if factory_func is None:
        raise ValueError(
            f"Plugin '{plugin_name}' is missing required create_instance_plugin(config) entry point."
        )
    return factory_func(plugin_config)


def get_plugin_config_model(plugin_name: str) -> type[BaseModel]:
    """
    Return the alert plugin module's config model class.
    Plugins must define get_config_model() -> type[BaseModel].
    """
    ensure_plugin_loaded("alerts", plugin_name)

    entry = _ALERT_REGISTRY[plugin_name]
    module = entry["module"]

    get_model = cast(
        Callable[[], type[BaseModel]] | None,
        getattr(module, "get_config_model", None),
    )
    if get_model is None:
        raise ValueError(
            f"Plugin '{plugin_name}' is missing required get_config_model() entry point."
        )
    model_cls = get_model()
    return model_cls
