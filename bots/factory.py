# bots/factory.py
# Copyright 2026 Clinton Bunch. All rights reserved.
# This source file is released under the Mozilla Public License 2.0

import importlib
import os
import logging
from bots.base import BaseChatBot

logger = logging.getLogger("bots.factory")

def create_bot(bot_type: str, name: str, endpoint: str, **kwargs) -> BaseChatBot:
    """
    Dynamically loads the bot driver and calls the standard entry point.
    """
    try:
        # Import the module: bots.webex_bot
        module = importlib.import_module(f"bots.{bot_type}")
        
        # Call the standard entry point (using getattr to handle missing function errors)
        factory_func = getattr(module, "create_instance_bot")
        return factory_func(name, endpoint, **kwargs)

    except (ImportError, AttributeError) as e:
        # Resolve the directory relative to this file to be safe
        bots_dir = os.path.join(os.path.dirname(__file__), ".")
        ignore_files = {"base.py", "factory.py", "__init__.py"}
        available = [
            f.replace(".py", "") 
            for f in os.listdir(bots_dir) 
            if f.endswith(".py") and f not in ignore_files
        ]
        
        logger.critical(f"Failed to load bot driver '{bot_type}': {e}")
        raise ValueError(f"Bot type '{bot_type}' not found. Available: {available}")
# -- End Function create_bot