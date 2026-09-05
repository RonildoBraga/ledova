# Marketing site

The public Ledova site: React, TypeScript and Vite, static output, no API calls.

## Local development

```bash
make install          # npm ci
cp .env.example .env  # or run scripts/init-local-env.py from the repository root
make dev              # http://localhost:5173
```

The `VITE_` values in `.env` are embedded in the browser bundle. Do not put a
secret in one. The local `.env` is gitignored.

`src/tokens.css` is generated from `packages/shared` by `make generate-tokens`
at the repository root. Do not edit it: CI regenerates it and fails on drift.

## Commands

| Command | Does |
| --- | --- |
| `make install` | Install dependencies |
| `make dev` | Start the Vite dev server |
| `make build` | Production build into `dist/` |
| `make preview` | Serve the built `dist/` locally |
| `make typecheck` | `tsc --noEmit` |
| `make lint` | ESLint |

`npm run format` and `npm run format:check` run Prettier over the package.

## Production build

`make build` writes the static bundle to `dist/`. `.deployment/Dockerfile.prod`
serves it through nginx with an `index.html` fallback for client-side routes.
This repository ships no deployment workflow: hosting and release authorization
belong to the environment owner.
