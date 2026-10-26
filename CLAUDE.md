# homeOBD

An OBD-style ("on-board diagnostics") web dashboard for apartment maintenance chores and
cleaning schedules, designed as a handheld scan tool ("APT-OBD"). Each chore is a diagnostic
code (e.g. `K2002`) that goes PEND → CONF → PERM as it becomes due and overdue, and lights
the CHK APT lamp. Self-hosted on a Raspberry Pi; later phases add IoT sensors that can raise
chores automatically.

- [docs/PLAN.md](docs/PLAN.md): roadmap, code/state rules, data model, API, current milestone.
- [prototype/](prototype/README.md): the original design reference for the look (colours,
  fonts, pixel screen, screen names). It is a starting point, not a spec.

## Precedence

The user's latest instructions win over anything earlier, including this file, PLAN.md and the
prototype. When they change a requirement, update this file (and PLAN.md) to match in the same
piece of work.

## UI rules (set by the user, 2026-10-26)

- Primary target: the home-screen app on an iPhone 17 / 17 Pro (402 x 874 pt), opened from
  Chrome or Safari. Check layouts at that size first; desktop is secondary.
- The scanner fills the whole phone screen. Every screen is the same size; long content
  scrolls inside the screen, never the page.
- Full height comes from `fitScreen()` in `scantool.js` setting `--app-height` on `<html>`:
  iOS home-screen apps with a see-through status bar report a viewport one status bar too short
  and only draw as far as the document reaches. Don't replace it with `100vh`, `100dvh` or a
  `position: fixed` layer; each of those left a gap or cropped the bottom on the iPhone.
- Touch-only: no up/down/ENTER/EXIT buttons. Tap rows to open them. Keyboard shortcuts may stay
  for desktop but must never be the only way to do something.
- Follow iOS conventions: `‹ Back` with a chevron icon at the left of the title bar, tap
  targets at least 44 pt, action buttons filled = primary and outlined = secondary,
  safe-area insets respected.
- One set of fonts everywhere, no iOS system font: VT323 for everything on the scanner screen
  (Back, rows, action buttons), Chakra Petch for the device body and the Setup page.
- No double-tap zoom on the app (`touch-action: manipulation`); pinch zoom stays available.
- Pages and assets are served with `Cache-Control: no-cache` so phones pick up deploys; bump
  the service worker's cache name when the app shell changes.

## Repository

- Remote: https://github.com/Vigneshsiva1/homeOBD (branch `main`)
- Working copy lives on the Pi at `/root/homeOBD`

## Git workflow rules

- **Ask before committing.** When a significant change has been made to the codebase, stop
  and ask the user whether to commit it, proposing a short commit message. Significant means
  any of: a feature or milestone step is working, several files changed, the database schema
  or API changed, deployment/systemd/config files changed, or a dependency was added/removed.
- Never commit or push without the user's yes. Ask separately before pushing to GitHub,
  unless the user's yes already covers both ("commit and push").
- Keep commits focused: one logical change per commit. Don't commit secrets, `.env` files,
  the SQLite database, or virtualenvs.

## Host constraints (Raspberry Pi 4, DietPi / Debian 13, aarch64)

- ~1 GB RAM and no swap: avoid Docker, heavy frontend build tooling, and anything that
  needs a compile step on the Pi. Prefer plain HTML/CSS/JS served by the backend.
- Python 3.13 and Node 26 are installed; the backend is Python (see PLAN.md).
- The app runs as a systemd service so it survives reboots.
- **Private only: home network + the user's tailnet.** Plain HTTP on the LAN
  (`http://192.168.0.157:8000`) and HTTPS through `tailscale serve` on the tailnet
  (`https://photostorage.tail82999e.ts.net`). Never Tailscale Funnel, port forwarding, public
  DNS or anything else that reaches the public internet. Don't add internet-facing features
  unless asked.
- This Claude Code session reaches the Pi over Tailscale: never stop, remove or reconfigure
  Tailscale in a way that could drop the connection.
