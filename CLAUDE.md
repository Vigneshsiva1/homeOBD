# homeOBD

An OBD-style ("on-board diagnostics") web dashboard for apartment maintenance chores and
cleaning schedules, designed as a handheld scan tool ("APT-OBD"). Each chore is a diagnostic
code (e.g. `K2002`) that goes PEND → CONF → PERM as it becomes due and overdue, and lights
the CHK APT lamp. Self-hosted on a Raspberry Pi; later phases add IoT sensors that can raise
chores automatically.

- [docs/PLAN.md](docs/PLAN.md): roadmap, code/state rules, data model, API, current milestone.
- [prototype/](prototype/README.md): the design reference. Match its look and behaviour.

## Repository

- Remote: https://github.com/Vigneshsiva1/homeOBD (branch `main`)
- Working copy lives on the Pi at `/root/homeOBD`

## Git workflow rules

- **Ask before committing.** When a significant change has been made to the codebase, stop
  and ask the user whether to commit it, proposing a short commit message. Significant means
  any of: a feature or milestone step is working, several files changed, the database schema
  or API changed, deployment/systemd/config files changed, or a dependency was added/removed.
- Never commit or push without the user's yes. Ask separately before pushing to GitHub.
- Keep commits focused: one logical change per commit. Don't commit secrets, `.env` files,
  the SQLite database, or virtualenvs.

## Host constraints (Raspberry Pi 4, DietPi / Debian 13, aarch64)

- ~1 GB RAM and no swap: avoid Docker, heavy frontend build tooling, and anything that
  needs a compile step on the Pi. Prefer plain HTML/CSS/JS served by the backend.
- Python 3.13 and Node 26 are installed; the backend is Python (see PLAN.md).
- The app runs as a systemd service so it survives reboots.
- **LAN only.** The app is used only on the home network: no port forwarding, public DNS,
  TLS certificates or tunnels. Don't add internet-facing features unless asked.
