# The Craticula public demo as one container image (story #3323, task #3786; NFR-02): the built AG Grid page and the demo API in one
# process on 8080, as a non-root user, fit for a read-only root file system (the only writable path is /tmp, an emptyDir in the
# cluster). Every base image is pinned by digest alone (a tag next to a digest is refused by Sonar rule docker:S8431), resolved on
# 2026-11-11: node:22-alpine, mcr.microsoft.com/dotnet/sdk:10.0, mcr.microsoft.com/dotnet/aspnet:10.0. To move one, resolve the new
# digest with `docker buildx imagetools inspect <image>:<tag>` and change it here.
# The API is built against the Craticula packages published on nuget.org (examples/demo/Directory.Packages.props), so the build needs
# network access to nuget.org and the npm registry, and nothing from csharp/.
# Build from the repository root:  docker build -f deploy/demo/Dockerfile -t craticula-demo:local .
FROM node@sha256:0e1754758c2df4cfa3e68d59e2e1b7374bb7fd9ea6328eaaacf15cc934af8202 AS web
WORKDIR /src/examples/demo/web
COPY examples/demo/web/package.json examples/demo/web/package-lock.json ./
RUN npm ci
COPY examples/demo/web ./
# tsc reads the column schema two folders up (src/columns.test.ts imports ../../orders.schema.json).
COPY examples/demo/orders.schema.json /src/examples/demo/orders.schema.json
RUN npm run build

FROM mcr.microsoft.com/dotnet/sdk@sha256:fe0fd4e93bd2fbb47c883b7a6369e5c8d3db8bf01cdc5981f6ee35fbdf3ff4fb AS api
WORKDIR /src/examples/demo
COPY examples/demo/global.json examples/demo/Directory.Build.props examples/demo/Directory.Packages.props ./
COPY examples/demo/orders.schema.json ./
COPY examples/demo/Api ./Api
RUN dotnet publish Api/Demo.Api.csproj -c Release -o /out

FROM mcr.microsoft.com/dotnet/aspnet@sha256:bfd912c83295ce66d4b706ebb8541b9f14259b0e76fbb88b2751f58ce2399d2e
WORKDIR /app
COPY --from=api /out ./
COPY --from=web /src/examples/demo/web/dist ./web
# The init container of each pod runs this (bash /app/seed.sh); the API container never does.
COPY deploy/demo/seed.sh ./seed.sh
# chmod in its own step: the publish agent builds with the classic builder, which rejects COPY --chmod (BuildKit only).
RUN chmod 0755 ./seed.sh
# AllowedHosts=* because the demo is reached under its public host names and, for the kubelet probes, by pod address: host filtering
# would answer 400 to both. DEMO_PUBLIC=1 turns the public-mode protections on; DEMO_PROVIDERS (the one engine) comes from the pod. HOME is /tmp so that
# nothing the runtime writes needs a writable root.
# Urls as well as ASPNETCORE_URLS: the API's appsettings.json sets "Urls" (127.0.0.1:5080) and, as app configuration, it beats the
# host variable ASPNETCORE_URLS; an environment variable named Urls beats appsettings.json.
ENV ASPNETCORE_URLS=http://+:8080 \
    Urls=http://+:8080 \
    DEMO_PUBLIC=1 \
    AllowedHosts=* \
    DEMO_WEB_DIR=/app/web \
    HOME=/tmp \
    DOTNET_BUNDLE_EXTRACT_BASE_DIR=/tmp \
    DOTNET_EnableDiagnostics=0
# A numeric user so that no scanner has to resolve a name; the cluster runs the same id.
USER 10001
EXPOSE 8080
ENTRYPOINT ["dotnet", "Demo.Api.dll"]
