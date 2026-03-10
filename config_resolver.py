# Thaum Engine v1.0.0
# Copyright 2026 Clinton Bunch. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

import os
import logging

def resolve_config_key(config_block, key_name, logger, required=True, default=None, allow_empty=False):
    """
    SysAdmin-grade config resolver. 
    Handles missing keys, empty strings (foot-aiming), and secure secret resolution.
    """
    val = config_block.get(key_name)

    # 1. Handle Missing Key
    if val is None:
        if required:
            raise ValueError(f"CRITICAL: '{key_name}' is required. See Thaum Documentation.")
        return default

    # 2. Handle Explicit "I want to disable this" (Empty String)
    if val == "":
        if not allow_empty:
            raise ValueError(f"CONFIGURATION ERROR: '{key_name}' cannot be empty.")
        else:
            logger.warning(f"SECURITY: '{key_name}' explicitly set to empty/disabled. Proceeding.")
            return None

    # 3. Resolve actual value (Literal, Env, Secret, or File)
    return _resolve_source(val, key_name, logger)

# -- End Function resolve_config_key

def _resolve_source(value, field_name, logger):
    """Internal helper to identify if the config value is a pointer or a literal."""
    
    # Handle non-string values (booleans, ints)
    if not isinstance(value, str):
        return value

    # Env Variable Source
    if value.startswith("env:"):
        env_var = value[4:]
        logger.verbose(f"[{field_name}] resolving from env: {env_var}")
        resolved = os.environ.get(env_var)
        if resolved is None:
            raise ValueError(f"Environment variable '{env_var}' not set.")
        return resolved.strip()

    # Orchestrator Secret Source (Systemd / K8s / Docker)
    elif value.startswith("secret:"):
        secret_name = value[7:]
        # Check systemd credentials first, then standard K8s/Docker path
        paths = [
            os.path.join(os.environ.get("CREDENTIALS_DIRECTORY", ""), secret_name),
            f"/run/secrets/{secret_name}"
        ]
        
        for path in paths:
            if os.path.isfile(path):
                logger.verbose(f"[{field_name}] resolving from secret: {path}")
                with open(path, "r") as f:
                    return f.read().strip()
        
        raise ValueError(f"Secret '{secret_name}' not found. Checked: {paths}")

    # Explicit File Source
    elif value.startswith("file:"):
        file_path = value[5:]
        logger.verbose(f"[{field_name}] resolving from file: {file_path}")
        if not os.path.isfile(file_path):
            raise ValueError(f"File not found at '{file_path}'.")
        with open(file_path, "r") as f:
            return f.read().strip()

    # Literal Value
    else:
        logger.verbose(f"[{field_name}] resolving from literal.")
        return value

# -- End Function _resolve_source