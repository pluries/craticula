# ADR-0010: The packages are pushed to nuget.org from a GitHub Actions workflow with Trusted Publishing

Status: Accepted   Date: 2026-11-06
Work items: #3706   Classification: Public

Amended by ADR-0012: the release pipeline starts the workflow and waits for it; the maintainer still approves the environment `nuget` on GitHub.

Amended by ADR-0011: the signing step is done by a Jenkins agent on the maintainer's Windows machine instead of by hand and an upload; the staging, the workflow and the push are unchanged.

It was accepted by the maintainer on 2026-11-11. It was written for readers outside the project: it names no private path or host.

## Context

- nuget.org advises against long-lived API keys for automated publishing. With Trusted Publishing, the CI system's short-lived OIDC token is
  exchanged for a temporary key that is valid for one hour and works once. nuget.org supports GitHub Actions and GitLab for this. Jenkins is not
  supported.
- The release is signed by hand. The maintainer signs the ten packages on a local machine with a one-time code from the phone app (ADR-0005), so
  the signed files have to reach the push step from outside the build system.
- The release pipeline runs in Jenkins. An earlier decision moved the whole release there and gave up Trusted Publishing: the push used a key
  limited to `Craticula.*`, valid for 12 months, stored as a Jenkins credential.
- Once an author certificate is registered on the nuget.org account, nuget.org accepts only packages signed with a registered certificate
  (ADR-0005). A leaked key alone can therefore not push an unsigned package or one signed by someone else.

## Decision

1. Jenkins keeps what it does today: the tag, the build from the public tag, the SBOMs, the pause for the signed upload and the verification of
   every signature and every package's content.
2. After the verification, Jenkins stages the ten signed packages, their SHA-256 hashes, the SBOMs and the release notes in a **draft** GitHub
   release, tells the maintainer which workflow to run, and pauses.
3. The maintainer runs the workflow `nuget-publish` (`.github/workflows/nuget-publish.yml`) for the tag and approves the GitHub environment
   `nuget`, which is limited to the `main` branch and has the maintainer as its required reviewer.
4. The workflow has three jobs, and the job that can ask for an OIDC token runs no code of the repository. The first job, `fetch`, reads the draft
   release and hands the files to the others as a workflow artifact that is kept for one day. It runs only from `main`, it is the only job with write
   permission on repository contents (reading a draft release needs it), and it has no OIDC token, no environment and no checkout. The second job,
   `check`, has read-only contents, no OIDC token and no environment. It checks out the scripts from the commit the workflow itself runs from (never from
   the release tag, which anyone with write access can create or move), and runs a check: the ten names, every signature against the pinned certificate
   fingerprint with a timestamp, the package identity (the id and the version inside each package), and every SHA-256 against the staged list. The third
   job, `publish`, runs in the environment `nuget`, holds only the OIDC token, runs no repository code, gets a temporary key through the NuGet login
   action and pushes with `--skip-duplicate`.
5. After the maintainer confirms in Jenkins, Jenkins checks that all ten packages are on nuget.org, makes the GitHub release public and writes the
   wiki page.
6. One setting of the release pipeline returns the push to Jenkins with a scoped key. It is the fallback if Trusted Publishing does not work at
   the first release.
7. The Trusted Publishing policy names the repository owner, the repository, the workflow file and the environment, allows pushing new packages
   and new versions, and is limited to the glob `Craticula.*`.

## Alternatives

- **Keep the push in Jenkins with the stored key.** The simplest option, and it was accepted before. It keeps a long-lived key, although the
  registered certificate limits what the key can do, and nuget.org advises against it.
- **Move the whole release to GitHub Actions.** The signing step needs a person with a phone code between the build and the push. Jenkins already
  waits for the upload without holding an agent, and the pipeline is built and tested. Moving it would duplicate that work for no gain.
- **Let Jenkins start the workflow through the GitHub API.** It saves one manual step, but the Jenkins token would then be allowed to run
  workflows, and the maintainer's approval of the environment would be the only gate. The maintainer keeps the click.
- **Attach a build attestation to the packages.** It would be untrue: the workflow does not build the signed files. No attestation is claimed.

## Consequences

- Positive: no long-lived NuGet key exists in Jenkins in the default mode. The push has its own audit trail (the deployment history and the
  approval). It follows nuget.org's advice.
- Negative: one release spans two systems. It needs one more manual step (run the workflow, approve the environment, confirm in Jenkins). A
  draft release holds the signed packages until the workflow has run; only people with write access can see a draft. While the run's artifact exists (one day), anyone who can see the public repository's runs can download the signed packages. They are not secret, since nuget.org publishes them minutes later. The signed files carry no
  build attestation, so a supply-chain score for the release provenance may stay lower.
- To check at the first run, because the documentation does not settle them: (a) the workflow's token can read the draft release's assets;
  (b) the policy's scopes accept packages that do not exist on nuget.org yet; (c) nuget.org accepts the signed packages as they are. If (a) or
  (b) fails, the maintainer uses the fallback of decision 6.

## What protects the push

- The signature against the pinned fingerprint is the control against a substituted package, together with nuget.org refusing any package that is not signed
  with the registered certificate (ADR-0005). The package identity check closes the case of a validly signed older package under a new file name.
- The SHA-256 list is staged next to the packages, so whoever can change a package can change the list. It catches damage in transit, not substitution.
- The maintainer should add a tag ruleset for `dotnet-v*` (no update, no deletion), because tags are not covered by the ruleset of `main`.

## Compliance

- Secrets: in the default mode no NuGet key is stored anywhere. The GitHub token stays a Jenkins credential limited to the one public
  repository. No personal data is involved.
- Approvals: the maintainer accepts this record as project lead and technical lead (solo mode). The policy on nuget.org and the environment on
  GitHub are created by the maintainer.
