# bots/factory.py
# Copyright 2026 Clinton Bunch. All rights reserved.
# This source file is released under the Mozilla Public License 2.0

import importlib
from bots.base import BaseBot

def create_bot(bot_type: str, name: str, endpoint: str, **kwargs) -> BaseBot:
    """
    Dynamically loads the bot driver and calls the standard constructor.
    'bot_type' corresponds to the filename (e.g., 'webex_bot')
    """
    try:
        # Import the module: bots.webex_bot
        module = importlib.import_module(f"bots.{bot_type}")
        
        # Call the standard entry point
        return module.create_instance_bot(name, endpoint, **kwargs)
    except (ImportError,ArithmeticError):
    # List files in bots/ to help the admin troubleshoot their typo
        import os
        available = [f for f in os.listdir("bots") if f.endswith(".py")]
        raise ValueError(f"Bot type '{bot_type}' not found. Available: {available}")
# -- End Function create_bot