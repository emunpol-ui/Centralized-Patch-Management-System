# CPMS Modern Design Update

## What changed
- **`static/css/dashboard.css`** — completely new design-system stylesheet (glassmorphism / iOS-inspired). This is a full replacement for your existing file at that path.
- **`templates/base.html`** — restructured the top navbar into a left sidebar + slim topbar (macOS/iPadOS style). All the same nav links, the same `request.url.path` active-state checks, the same `{% if administrator %}` block, and the same `id="logoutButton"` your `dashboard.js` hooks into. On mobile/tablet it collapses into a slide-in drawer using Bootstrap's built-in `offcanvas-lg` component (no new JS needed).
- **`templates/login.html`** — same form, same `id`s, same fetch call to `/api/admin/login`, just a glass card on a soft gradient background.
- **All 13 other templates in `templates/dashboard/`** — copied over **unchanged**. I inspected every file first: they all build on plain Bootstrap 5 classes (`.card`, `.btn`, `.badge.text-bg-*`, `.table`, `.form-control`, `.modal`, `.alert`, functional classes like `.delete-client-btn`/`.cancel-deployment-btn`/`.deploy-client-checkbox`, etc.). The new stylesheet reskins those Bootstrap classes globally — and Bootstrap's own status colors (`--bs-success`, `--bs-warning`, ...) are overridden as CSS variables — so every page, including the dynamic `{{ row.badge_class }}` badges, picks up the new look automatically with zero template/logic changes.

## Nothing else touched
No routes, API calls, form field names, JS behavior, or template logic were changed. `home.html`'s local `<style>` block (hover effect on the stat cards) was left as-is; it layers on top of the new card styling harmlessly.

## To install
1. Replace your `static/css/dashboard.css` with the one in this zip.
2. Replace `templates/base.html` and `templates/login.html`.
3. Leave the rest of `templates/dashboard/*.html` as they already are (or drop in the copies here — they're identical to what you have).
