# Thaum System Architecture

## Overview

Thaum is a modular, plugin-driven orchestration framework designed for
deterministic, admin-friendly operations. Its architecture emphasizes
predictable lifecycle sequencing, clean separation of concerns, and
strict avoidance of import-time side effects. The system is composed of
a central server process, a shared database, a plugin layer, and one or
more bot instances.

------------------------------------------------------------------------

## 1. Bootstrap Sequence

Thaum uses a four-phase bootstrap process to ensure deterministic
initialization.

### **Phase 1 - Load Raw Configuration**

- server.py loads all TOML configuration files via config.py.

- Configuration is parsed into:

  - ServerConfig

  - BotConfig objects (one per bot key)

- No plugin modules are imported.

- No validation beyond syntactic correctness.

- No side effects.

### **Phase 2 - Load Plugin Modules and Typed Config Models**

- load_plugins() imports each plugin module.

- Each plugin module:

  - Defines ORM models as subclasses of EmeraldDB.

  - Exposes a get_plugin_config_model() function.

- Typed plugin config objects are created and validated.

- Each plugin config stores a reference to its plugin ClassType.

- Still **no plugin objects are instantiated**.

### **Phase 3 - Initialize Database**

- After all plugin modules are imported, emerald_utils.db.init_db() is
  called.

- This creates all ORM tables defined by plugins.

- The DB engine and session factory are initialized.

- This is the first moment where side effects occur.

### **Phase 4 - Instantiate Bots and Plugins**

- initialize_bots() constructs bot objects from BotConfig.

- For each bot:

  - Retrieve the bot's AlertPluginConfig.

  - Instantiate the plugin using its stored ClassType.

  - Attach plugin to bot.

  - Register handlers.

  - Perform leader-only initialization.

- After this phase, the system is fully wired.

------------------------------------------------------------------------

## 2. Configuration Model

Thaum uses a layered configuration model.

### **ServerConfig**

- Logging configuration

- Lookup plugin configuration

- Global defaults

- Database URL

### **BotConfig**

- BaseChatBotConfig

- AlertPluginConfig

- Responder lists

- Room templates

### **PluginConfig**

Each plugin config contains:

- Typed Pydantic config

- Reference to plugin ClassType

- Raw configuration for plugin-specific behavior

This structure mirrors the plugin object hierarchy and ensures clean
separation between configuration and instantiation.

------------------------------------------------------------------------

## 3. Plugin Architecture

Plugins are first-class components in Thaum.

### **Plugin Module Requirements**

Each plugin module must:

- Define ORM models as subclasses of EmeraldDB.

- Provide a get_plugin_config_model() function.

- Avoid import-time side effects.

- Keep constructors free of DB access until after Phase 3.

### **Plugin Object Lifecycle**

Plugin constructors may:

- Open DB sessions

- Load cached state

- Register webhook handlers

- Schedule periodic tasks

- Load secrets

- Attach themselves to bots

Plugins must not:

- Perform DB operations before Phase 3

- Register handlers before bot instantiation

- Trigger background tasks before initialization completes

------------------------------------------------------------------------

## 4. Database Layer

Thaum uses a shared database for:

- Alert lifecycle tracking

- Pending event buffering

- Plugin state

- Identity cache

- Leader election metadata

### **DB Initialization Rules**

- All ORM models must be imported before init_db().

- No plugin may create tables independently.

- All migrations (future) must run after plugin import.

------------------------------------------------------------------------

## 5. Event Processing and Lifecycle

Thaum processes events from external systems (e.g., alerting platforms)
in a deterministic manner.

### **Alert Lifecycle**

- Alerts are created with a short_id stored in extraProperties.

- Webhooks may arrive out of order.

- Thaum uses a DB-backed pending-event buffer to handle:

  - ack before create

  - escalate before ack

  - delayed create events

### **Pending Create Handling**

- When an alert is sent, Thaum immediately notifies the room with the
  short_id.

- A DB row is created with state = pending_create.

- When the create webhook arrives, the alert is activated.

- A watchdog timer marks alerts as failed if creation does not complete.

------------------------------------------------------------------------

## 6. Logging and Diagnostics

Thaum uses structured logging with multiple levels:

- INFO - normal operational messages

- NOTICE - important but non-urgent events

- VERBOSE - routine status messages

- DEBUG - developer-level detail

- SPAM - full diagnostics, including JSON bodies and stack traces

Multi-line output uses the blob helper for readability.

Stack traces are only emitted at SPAM level.

------------------------------------------------------------------------

## 7. Import-Time Side-Effect Rules

To maintain deterministic startup:

- No plugin may perform DB access during import.

- No plugin may register handlers during import.

- No plugin may start background tasks during import.

- Importing a plugin module must only:

  - define ORM models

  - define config models

  - expose plugin class

------------------------------------------------------------------------

## 8. Directory Structure

A typical Thaum deployment uses:

  ------------
  thaum/\
  server.py\
  config.py\
  bots/\
  plugins/\
  db/\
  utils/\
  logging/\
  docs/

  ------------

This structure keeps concerns isolated and predictable.

------------------------------------------------------------------------

## 9. Operational Philosophy

Thaum is designed around:

- Deterministic behavior

- Admin-friendly operations

- Predictable concurrency

- Clear separation of concerns

- Minimal magic

- Explicit lifecycle sequencing

- Low-noise logging

- Safe, humane on-call workflows

------------------------------------------------------------------------

## 10. Summary

Thaum's architecture is built to be:

- Modular

- Predictable

- Maintainable

- Extensible

- Operationally safe

By enforcing strict bootstrap sequencing, clean plugin boundaries, and
disciplined logging and exception handling, Thaum provides a stable
foundation for complex operational automation.
