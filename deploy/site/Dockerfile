# The Craticula documentation site as a container image (story #3322, task #3327): the static pages built by scripts/build_site.py,
# served by an unprivileged nginx on 8080 with a read-only root filesystem. Both base images are pinned by digest alone (NFR-02;
# a tag next to a digest is refused by Sonar rule docker:S8431): python:3.12-alpine and nginxinc/nginx-unprivileged:stable-alpine-slim,
# resolved on 2026-10-30. To move one, resolve the new digest with `docker buildx imagetools inspect <image>:<tag>` and change it here.
# Build from the repository root:  docker build -f deploy/site/Dockerfile -t craticula-site:local .
FROM python@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8 AS build
WORKDIR /src
COPY . .
RUN python3 scripts/build_site.py --out /out

FROM nginxinc/nginx-unprivileged@sha256:5d8bb9437d74a600ec5dbf90c035451c724dc33eac8d3a71078f6f8612c345f6
COPY deploy/site/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /out /usr/share/nginx/html
EXPOSE 8080
