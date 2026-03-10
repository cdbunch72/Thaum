# Thaum Engine v1.0.0
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import os
import importlib.util
import inspect
import logging
from log_setup import SHOW_STACKTRACE
from alerts.base import BaseAlertPlugin

# The global registry where we store our dynamically loaded plugins
PLUGIN_REGISTRY = {}

def load_plugins(alerts_dir="./alerts"):
    """
    Scans the alerts directory, imports modules, and registers classes 
    inheriting from BaseAlertPlugin.
    """
    logger = logging.getLogger("plugin_loader")
    
    if not os.path.isdir(alerts_dir):
        logger.error(f"Alerts directory '{alerts_dir}' not found. No plugins loaded.")
        return

    for filename in os.listdir(alerts_dir):
        # Only process .py files, ignore hidden/dunder files, and skip the base class
        if not filename.endswith(".py") or filename.startswith("__") or filename == "base.py":
            continue

        module_name = filename[:-3]
        file_path = os.path.join(alerts_dir, filename)
        
        try:
            # Dynamically import the module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find all classes that inherit from BaseAlertPlugin
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseAlertPlugin) and obj is not BaseAlertPlugin:
                    PLUGIN_REGISTRY[name] = obj
                    logger.debug(f"Registered plugin class: {name} (from {filename})")
                    
        except Exception as e:
            # SysAdmin-friendly error reporting: Which file, what error, and optional stack trace
            logger.error(
                f"Failed to load plugin '{filename}': {e.__class__.__name__} - {str(e)}", 
                exc_info=SHOW_STACKTRACE
            )
# -- End Function load_plugins

def get_plugin(plugin_name, plugin_config):
    """
    Factory function to instantiate a plugin from the registry.
    """
    if plugin_name not in PLUGIN_REGISTRY:
        available = ", ".join(PLUGIN_REGISTRY.keys())
        raise ValueError(f"Plugin '{plugin_name}' not found. Available: {available}")
    
    # Instantiate the plugin with its configuration
    return PLUGIN_REGISTRY[plugin_name](**plugin_config)
# -- End Function get_plugin