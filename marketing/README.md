# Ledova Marketing Site

React + TypeScript + Vite site for the Ledova experimental reference implementation.

---

## Local Development

```bash
# Install dependencies (first time only)
make install

# Create public local configuration
cp .env.example .env

# Start dev server at http://localhost:5173
make dev
```

The `VITE_` values in `.env` are embedded in browser code. Do not put secrets in
them. The local `.env` file is ignored by Git.

---

## Production Build

Run `make build` to create the static bundle in `dist/`. This repository does
not include a deployment workflow; hosting and release authorization are the
responsibility of the environment owner.

The production container serves the Vite single-page application through
nginx and falls back to `index.html` for client-side routes.

---

## Useful Commands

| Command      | Description                                 |
| ------------ | ------------------------------------------- |
| `make dev`   | Start local dev server                      |
| `make build` | Production build (output in `dist/`)        |
| `make lint`  | Format + lint with auto-fix                 |
| `make check` | Full local check (format, lint, type-check) |
| `make test`  | Check the production nginx configuration    |
