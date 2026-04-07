# Thaum Style Guide

This document defines the coding, logging, formatting, and structural
conventions used throughout the Thaum codebase. These rules exist to
preserve clarity, maintainability, and operational safety in a system
that handles real-world alerting, plugins, and lifecycle orchestration.

------------------------------------------------------------------------

## 1. Purpose and Philosophy

Thaum's style guide is built around these principles:

- **Clarity over cleverness**

- **Determinism over magic**

- **Operational safety over convenience**

- **Explicit structure in a whitespace-sensitive language**

- **Low-noise, high-signal logging**

- **Predictable behavior under load**

These rules ensure that future contributors-and future you-can
understand the system quickly and safely.

------------------------------------------------------------------------

## 2. Line Length Standard

Thaum uses a **132-column line limit**.

### Rationale

- Preserves indentation structure in deeply nested logic.

- Keeps end-of-block comments readable.

- Prevents excessive wrapping in structured logging.

- Supports multi-argument function calls and plugin wiring.

- Modern tools (Cursor, VS Code, PuTTY, Windows Terminal) support 132
  columns easily.

### Exceptions

- Long URLs

- Intentionally formatted multi-line strings

- Auto-generated code

------------------------------------------------------------------------

## 3. End-of-Block Comments

Python lacks explicit block delimiters, so Thaum uses end-of-block
comments to make structure visible.

### Required End-of-Block Comments

- Every **function**, **method**, and **class** ends with:

  - \# end def function_name

  - \# end class ClassName

### Conditional and Loop Blocks

Use end-of-block comments for:

- Blocks longer than \~15 lines

- Blocks nested 3+ levels deep

- Any block where indentation alone is ambiguous

Examples:

  -----------------------------------------------------------------------
  \# end if plugin_enabled\
  \# end for bot in bots\
  \# end try: DB initialization
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 4. Logging Conventions

Thaum uses structured, multi-level logging with strict semantics.

### Logging Levels

- **INFO** - Normal operational messages.

- **NOTICE** - Important but non-urgent events.

- **VERBOSE** - Routine status messages.

- **DEBUG** - Developer-level detail without stack traces.

- **SPAM** - Full diagnostics, including JSON bodies, object dumps, and
  stack traces.

### Multi-Line Output

Use the **blob helper** for:

- JSON dumps

- Object dumps

- Stack traces

- Multi-line diagnostics

This ensures consistent indentation and readability.

### Stack Traces

- Only emitted at **SPAM** level.

- Wrapped using the blob helper.

- Never appear in INFO/NOTICE/VERBOSE/DEBUG.

------------------------------------------------------------------------

## 5. Exception Handling

Exceptions must be used sparingly and intentionally.

### Rules

- Do **not** use exceptions for control flow.

- Catch exceptions at the **outer boundary** of handlers, plugins, and
  background tasks.

- Convert exceptions into structured logs.

- Never allow exceptions to escape into the event loop.

### Canonical Pattern

  -----------------------------------------------------------------------
  try:\
  \...\
  except KnownError as e:\
  logger.log(LogLevel.NOTICE, \"Known error occurred: %s\", e)\
  return\
  except Exception as e:\
  logger.error(\"Unexpected exception: %s\", e)\
  if logger.isEnabledFor(LogLevel.SPAM):\
  logger.log(LogLevel.SPAM, \"%s\", blob(e))\
  return\
  \# end try
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 6. Import-Time Side-Effect Rules

To maintain deterministic startup:

### Forbidden During Import

- DB access

- Handler registration

- Background task creation

- Network calls

### Allowed During Import

- Defining ORM models as subclasses of GemstoneDB

- Defining config models

- Exposing plugin classes

Importing a plugin module must be a **pure operation**.

------------------------------------------------------------------------

## 7. Plugin Constructor Rules

Plugin constructors may:

- Open DB sessions

- Load cached state

- Register webhook handlers

- Schedule periodic tasks

- Load secrets

- Attach themselves to bots

Plugin constructors must **not**:

- Perform DB operations before init_db()

- Register handlers before bot instantiation

- Trigger background tasks before initialization completes

------------------------------------------------------------------------

## 8. Naming Conventions

### Modules

- Lowercase with underscores: alert_plugin.py

### Classes

- PascalCase: AlertPlugin, BotManager

### Functions and Methods

- snake_case: bootstrap(), initialize_bots(), ensure_plugin_loaded()

### Constants

- UPPER_SNAKE_CASE: DEFAULT_TIMEOUT

### Private Members

- Leading underscore: \_load_config()

------------------------------------------------------------------------

## 9. Directory Layout

A typical Thaum project uses:

  -----------------------------------------------------------------------
  app.py\
  bootstrap.py\
  web.py\
  config.py\
  bots/\
  ....plugins/\
  alerts/\
  ....plugins/\
  ..lookup/\
  ....plugins\
  tests/\
  thaum/
  -----------------------------------------------------------------------

  -----------------------------------------------------------------------

This structure keeps concerns isolated and predictable.

------------------------------------------------------------------------

## 10. Code Structure and Readability

### General Rules

- Prefer clarity over compactness.

- Avoid deeply nested logic when possible.

- Use helper functions to break up long workflows.

- Keep constructors lightweight.

- Keep plugin logic isolated from bot logic.

### Comments

- Use comments to explain *why*, not *what*.

- Use end-of-block comments to clarify structure.

- Avoid redundant comments.

------------------------------------------------------------------------

## 11. Operational Safety Rules

- Logging must never leak secrets.

- SPAM mode must be explicitly enabled.

- All external events must be validated.

- All webhook handlers must be exception-safe.

- DB writes must be atomic and consistent.

------------------------------------------------------------------------

## 12. Summary

Thaum's style guide enforces:

- Clear structure

- Predictable behavior

- Safe operations

- Maintainable code

- Explicit lifecycle boundaries

By following these conventions, Thaum remains readable, stable, and
friendly to both developers and operators.
