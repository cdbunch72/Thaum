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
from typing import Any, Callable, Dict, TypedDict, cast

from pydantic import BaseModel
from log_setup import should_log_exception_trace

from alerts.base import BaseAlertPlugin

# Global registry: plugin module name -> loaded module + plugin class.
PLUGIN_REGISTRY: Dict[str, _PluginRegistryEntry] = {}


class _PluginRegistryEntry(TypedDict):
    module: types.ModuleType
    plugin_class: type[BaseAlertPlugin]


def _load_plugin_module(plugin_name: str) -> None:
    logger = logging.getLogger("plugin_loader")
    module = importlib.import_module(f"alerts.plugins.{plugin_name}")
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

    PLUGIN_REGISTRY[plugin_name] = {
        "module": module,
        "plugin_class": plugin_classes[0],
    }
    logger.debug(
        "Registered plugin module: %s (class %s)",
        plugin_name,
        plugin_classes[0].__name__,
    )


def ensure_plugin_loaded(plugin_name: str) -> None:
    if plugin_name in PLUGIN_REGISTRY:
        return

    _load_plugin_module(plugin_name)


def load_plugins(required_plugins: list[str]) -> None:
    """Load only explicitly requested plugin modules."""
    logger = logging.getLogger("plugin_loader")

    for plugin_name in required_plugins:
        try:
            ensure_plugin_loaded(plugin_name)
        except Exception as e:
            logger.error(
                f"Failed to load plugin '{plugin_name}': {e.__class__.__name__} - {str(e)}",
                exc_info=should_log_exception_trace(),
            )
            raise


def get_plugin(plugin_name: str, plugin_config: BaseModel) -> BaseAlertPlugin:
    """
    Instantiate an alert plugin from a validated Pydantic config instance.
    Plugin modules must expose create_instance_plugin(config_model_instance).
    """
    ensure_plugin_loaded(plugin_name)

    entry = PLUGIN_REGISTRY[plugin_name]
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
    Return the plugin module's required config model class.
    Plugins must define get_config_model() -> type[BaseModel].
    """
    ensure_plugin_loaded(plugin_name)

    entry = PLUGIN_REGISTRY[plugin_name]
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
