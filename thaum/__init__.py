# Thaum Engine v1.0.0
# Copyright 2026 <<Name>>. All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

from typing import Dict
from bots.base import BaseBot

# Global registry for bot appliances
BOTS: Dict[str, BaseBot] = {}

from thaum.engine import create_incident_room, acknowledge_incident
from thaum.handlers import bind_thaum_handlers