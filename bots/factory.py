# bots/factory.py
# Copyright 2026 Clinton Bunch. All rights reserved.
# SPDX-License-Identifier: MPL-2.0
# This source file is released under the Mozilla Public License 2.0

import importlib
import os
import logging
from pydantic import ValidationError
from typing import Any
from bots.base import BaseChatBot

logger = logging.getLogger("bots.factory")

def create_bot(bot_type: str, config_raw: dict[str, Any]) -> BaseChatBot:
    """
    Dynamically loads the bot driver and calls the standard entry point.
    """
    bot_name=config_raw.get('name','<unknown>')
    try:
        module = importlib.import_module(f"bots.{bot_type}")
        
        # Call the standard entry point (using getattr to handle missing function errors)
        ConfigModel=module.get_config_model()
        cfg=ConfigModel(**config_raw)
        factory_func = getattr(module, "create_instance_bot")
        return factory_func(cfg)

    except (ImportError) as e:
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
    except AttributeError as e:
        logger.critical(f"Bot module '{bot_type}' missing required entry point: {e}")
        raise

    except ValidationError as e:
        logger.critical(f"Invalid configuration for bot '{bot_name}': {e}")
        raise

    except Exception as e:
        logger.critical(f"Bot '{bot_name}' failed to construct: {e}")
        raise

# -- End Function create_bot