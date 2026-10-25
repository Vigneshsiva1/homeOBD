# Prototype

Design reference for the homeOBD dashboard. Not served by the app.

- `index.html` — the original self-contained export (design, fonts and runtime packed into
  one file). Open it in a browser to click through the prototype.
- `template.html` — the design unpacked from `index.html` so it can be read and diffed: the
  markup plus the `Component` class holding all screen logic and mock data. It references
  packed assets by id, so it does not render on its own.

The real frontend (Milestone M2 in [docs/PLAN.md](../docs/PLAN.md)) recreates this design in
plain HTML/JS fed by the API.
