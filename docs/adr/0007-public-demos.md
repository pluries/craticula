# ADR-0007: The public demos are read-only by design and protect themselves

Status: Accepted   Date: 2026-11-11
Work items: #3323, #3784, #3785, #3787, #3789   Classification: Public

The maintainer accepted this record on 2026-11-11 as project lead and technical lead (solo mode), after answering the four design questions below. It names no private path or host.

## Context

- The launch wants two public demo sites, one on PostgreSQL and one on MongoDB, with synthetic data (the launch spec, FR-10 to FR-16 and FR-24).
- They run in a namespace that other services of the maintainer share, behind Cloudflare and an ingress controller. A flood on a demo must not take capacity from the neighbours.
- The grid itself needs `POST` (the Server-Side Row Model sends its request in a body), so "no `POST`" is not the way to make the demo read-only.

## Decision

1. **Read-only at three levels.** The demo API in public mode (`DEMO_PUBLIC=1`) accepts only the grid routes (`POST /api/{engine}/rows|values|export.csv|query`) and answers 405 to everything else, including `PUT` and `DELETE`. The library compiles no write statement from a request. The database account the API uses can only read (PostgreSQL `GRANT SELECT`, MongoDB role `read`), and the account that seeds the data exists only in the init step of the pod.
2. **Data is ephemeral and reseeded whenever the database pod starts** from the repository's synthetic seed, with no volume. The seeding container sits in the database pod itself, so a recreated database pod comes back with the data and the read-only account. The seed prints a checksum computed from the database after the load, so a restart can be checked.
3. **The rate limit lives in the demo app**: 60 requests a minute per client address (for IPv6, per /64 network, so one host cannot rotate through its own range). The address is the value of `CF-Connecting-IP`, trusted **only** when the connecting peer is inside the configured proxy range (`DEMO_TRUSTED_PROXIES`, empty by default, so a developer machine ignores the header). A network policy lets only the ingress controller reach the demo pods.
4. **A second line behind the per-address limit**: a global cap per pod (`DEMO_GLOBAL_LIMIT`, 600 requests a minute by default). It protects the database and the neighbours, not the demo's own availability: someone who can rotate the header can spend the cap and make the demo answer 429 to everyone. The probe route `/api/health` is exempt from both limits, so a spent cap never makes the pod unready.
5. **A query that runs longer than 2 seconds is cut.** For PostgreSQL the database cancels it: `statement_timeout` on the read-only role. For MongoDB the cut is the app's: the gate cancels the operation after 2 seconds. A database-side `maxTimeMS` is not possible today, because the library's MongoDB adapter has no such option and driver 3.13 ignores `timeoutMS` in a connection string. A follow-up work item asks the library for it. A response that has already started when the cut fires is aborted, never ended as a complete-looking truncated file.
6. **One image, run twice.** One hardened image (non-root, read-only root file system, base images pinned by digest) serves the page and the API. `craticula-pg` and `craticula-mongo` differ only in their environment (`DEMO_PROVIDERS`).
7. **The maintainer is alerted** by a scheduled check of both addresses; three failures in a row (15 minutes) raise the alert.

## The assumption behind decision 3

The per-address limit is only as honest as `CF-Connecting-IP`. Cloudflare overwrites that header, but a client that reaches the origin around Cloudflare can set it to anything. We therefore assume the origin is reachable **only through Cloudflare**, and we do not rely on that assumption alone: decision 4 caps the whole pod, and the network policy limits who can reach the pod at all. If the assumption fails, a visitor can bypass the per-address limit but still cannot exceed the pod's cap, at the cost described in decision 4.

## Alternatives

- **Limit in the ingress** (`limit-rpm` annotation). Needs the shared ingress controller to trust Cloudflare's forwarded address, a change outside our namespace that affects the maintainer's other services.
- **Persistent volumes with a seed on first start.** Survive restarts, but "after a restart the data equals the seed" would then need a reseed job and a volume to look after.
- **Two images, one for the page and one for the API.** Closer to the development layout, but two images to pin by digest and two probes per demo.
- **Refuse every `POST`.** Breaks the grid.

## Consequences

- The demo API gains public-mode code and settings; without `DEMO_PUBLIC=1` it behaves as before, so the local demo and its smoke test are unchanged.
- The demos are best effort (no SLA, the launch spec NFR-06); a maintenance window can take them down.
- The cluster files are drafted in the private repository and applied by the maintainer; a secret is never in a file.
- A new threat-model entry covers flooding, a forged address header, a crafted write filter, a slow query and the shared namespace.

## Compliance

No personal data: the seed is synthetic. No new library: the rate limiter is part of the framework. The Docker Hub repository and the cluster workloads are maker-created resources, recorded in the release checklist by the documents story.
