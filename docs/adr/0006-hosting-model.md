# ADR-0006: The docs site is a static image on the maker's own hosting, behind Cloudflare

Status: Accepted   Date: 2026-11-23
Work items: #3332, #3322, #3329, #3390, #3331   Classification: Public

The maintainer accepted this record on 2026-11-23 as project lead and technical lead (solo mode). It is marked Public because it names no cluster, host address, credential, secret name or internal URL. The public site host (`craticula.pluries.dev`) and the Docker Hub repository (`elieabouaad/craticula-site`) are already public.

## Context

- The launch spec wants the docs site at `https://craticula.pluries.dev` with a valid certificate, no manual renewal and a permanent redirect from `http` (FR-06, FR-07). Every request to the apex and `www` names must land on the site's host (FR-08).
- The maintainer already runs a cluster and a Cloudflare account. The yearly budget leaves no room for paid hosting (NFR-07).
- A page on GitHub Pages was prepared first. It serves only a `github.io` address or a custom domain whose DNS the maintainer must hand to GitHub, and it cannot set the security headers or the redirects the spec asks for.
- A DNS record that outlives the thing it points to can be claimed by someone else (dangling DNS, risk R12).
- A pipeline that can write to the deployment repository can change what runs on the maintainer's hosting, so its key needs a narrow scope (NFR-12).

## Decision

1. **The site is one static image.** `scripts/build_site.py` builds the pages. A small web server image serves them: non-root, read-only root file system, base images pinned by digest (NFR-02). The image is published to a private Docker Hub repository by a Jenkins job on a dedicated `docker-publish` agent, using a Jenkins credential (#3390).
2. **Deployment is a commit, not a push to the cluster.** The publish job commits the new image digest to the GitOps repository, and the cluster's GitOps controller applies it (#3329). The job's key belongs to a dedicated service identity that has Contribute on that one repository only. It is valid for at most 12 months and is readable only by the publish job (NFR-12). The job changes one overlay file and refuses any other change.
3. **Cloudflare sits in front.** DNS for the site is proxied. SSL mode is Full (strict), with a Cloudflare origin certificate between Cloudflare and the origin. The minimum TLS version is 1.2 (NFR-01).
4. **"Always Use HTTPS" is on (decided 2026-11-23).** The origin does not answer `http` on port 80 (a visitor who reached it would see a 522). Cloudflare therefore answers every `http` request itself with a `301` to `https`.
5. **The site is watched from outside.** `scripts/check-site.sh` checks redirects, headers and the certificate the visitor sees. Its opt-in edge mode (`CHECK_SITE_EDGE_HTTPS=on`) expects Cloudflare's `301`. The Jenkins job `craticula-site-watch` runs it every 5 minutes and alerts through the existing Discord webhook credential when the certificate has 14 days or less left, or the site has been down for 15 minutes (NFR-09).
6. **DNS teardown rule (R12).** When a site or a demo is removed, its DNS record is removed in the same change. The change that deletes the manifests is not complete until the record is gone. The maintainer checks the list of DNS records at each release.
7. **GitHub Pages stays off.** The repository variable `DOCS_PAGES` is not set, so the `deploy` job of the docs workflow is skipped. The `site` job keeps checking the build.

## Alternatives

- **GitHub Pages.** Free and simple, but it needs the domain's DNS to point at GitHub, cannot send our headers, and cannot give the spec's redirects (FR-07, FR-08). It also leaves the site and the demos on two different hosting paths. Kept off, and the switch-on steps stay in the maintainer's private notes in case the maintainer changes this record.
- **A managed platform (a static host or a container service).** Less work to run, but a yearly cost the budget does not cover (NFR-07), and one more account holding a deploy credential.
- **Serve from the origin with the origin answering `http` and a `308`.** This is what the spec first asked for (FR-07). It needs "Always Use HTTPS" off, port 80 open to the internet on the origin, and a redirect rule inside the site's server. It was dropped: the origin stays closed on port 80 and Cloudflare does the redirect.

## Consequences

- **Deviation from the spec, recorded.** FR-07 and the spec's Cloudflare note say the visitor gets a `308` from the origin. With this decision the visitor gets a `301` from Cloudflare. A `301` is permanent too, so the intent holds. A `301` may turn a `POST` into a `GET`; the site has no `POST`. The spec text is updated with this record.
- **Check script.** By default `scripts/check-site.sh` still expects the origin's `308`. The edge mode (`CHECK_SITE_EDGE_HTTPS=on`) is opt-in and the site watch sets it. It passed 73 of 73 checks on 2026-11-23.
- Traffic reaches the site only through Cloudflare. The demo limits (ADR-0007) rely on the same assumption.
- The site is best effort, like the demos (NFR-06). A Cloudflare outage takes it down.
- Rotating the GitOps key every 12 months is a calendar task for the maintainer (it is on the maintainer's private checklist).
- The remaining checks (Tech Lead approval of base image digests, a credential that only the publish job can use, and the first digest commit and sync) are listed on the maintainer's private checklist as open until the maintainer proves them.

## Compliance

- **No personal data.** The site is public documentation.
- **Secrets.** Cloudflare, Docker Hub, GitOps and Discord values live only in the vault and the Jenkins credential store, never in a file, an image or a log (NFR-01).
- **New tooling.** The Docker Hub repository, the Cloudflare settings and the GitOps identity are maintainer-created resources. The maintainer's private checklist records them.
- **Approval.** Solo mode (the project's recorded solo mode): the maintainer decides as project lead and technical lead. Nothing is pending on another role.
