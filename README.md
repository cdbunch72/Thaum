# Thaum
## Chat‑Driven On‑Call and Team Alerting

Thaum was written to solve the problem of users who expect operations to be actively monitoring a chat room all night in case they need help.  It is a modular framework to tie a chat bot to an on-call alerting system. 

I have implemented Webex and Jira Service Manager Ops.  But plugins could be written for PagerDuty or even something as simple as a team broadcast via Pushover.  A plugin could also be written to make it a Teams bot instead of webex.

I have over 30 years of experience in IT operations and I know the pain of on-call.  I also know the pain of trying to use logging to troubleshoot an operational system. (Stacktraces are not logs!)  I built something I want to use, and I hope you'll find it useful too.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — bootstrap, config model, logging, plugins.
- [Podman/systemd quickstart](docs/quickstart/README.md) — Quadlet deployment with encrypted credentials.
- [Style guide](docs/STYLE_GUIDE.md) — code and test conventions.
- [Admin log level API](docs/admin-log-level.md) — signed runtime log level changes.
- [Release notes](RELEASE_NOTES.md)