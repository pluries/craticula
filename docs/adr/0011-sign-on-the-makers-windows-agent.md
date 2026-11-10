# ADR-0011: The release packages are signed by a Jenkins agent on the maker's Windows machine

Status: Accepted   Date: 2026-11-10
Work items: #3765   Classification: Public

Accepting this record is the maintainer's decision. It was written for readers outside the project: it names no private path or host.
It changes how ADR-0005 and ADR-0010 sign the packages. The certificate itself (ADR-0005) and the push through Trusted Publishing
(ADR-0010) stay as they are.

## Context

- ADR-0005 chose Certum's cloud certificate, whose key never leaves Certum. Every signing session needs a one-time code from the
  maintainer's phone. ADR-0005 and ADR-0010 had the maintainer sign the ten packages by hand on a local machine and upload a zip to the
  release job.
- The browser upload to the release job failed in practice. In three real runs the controller gave up reading the form after 30 seconds,
  and Jenkins treats a failed form as an abort. Each failed run had already created a release tag, and tags are never rolled back, so
  every failure used up a version number.
- `dotnet nuget sign` reads the certificate from the operating system's certificate store or from a file. On Windows, SimplySign Desktop
  puts the cloud certificate into the store. The Linux client offers a PKCS#11 module that `dotnet nuget sign` does not read, and nothing
  standard builds a NuGet signature from a remote key on Linux.
- On 2026-11-09 a test job on the maintainer's Windows machine, connected to Jenkins as an agent in the maintainer's logged-in session,
  found the certificate, signed a package with the pinned fingerprint and an RFC 3161 timestamp in about three seconds, and
  `dotnet nuget verify --all` passed.
- Certum's terms of use for non-qualified certificates (version 1.4) require the subscriber to protect the private key and to
  control its use. They say nothing about automation. Certum's resellers state that CI/CD is not supported, which means no official
  support, not a prohibition.

## Decision

1. The release job signs the ten packages on a **signing agent**: the maintainer's Windows machine, connected to Jenkins over WebSocket
   with its own label, running as the maintainer in an interactive session. Only the release job uses that label.
2. Early in the run, before the tag exists, a short step on the signing agent checks that the certificate with the pinned fingerprint
   is available. If it is not, the run stops and tells the maintainer to log in to SimplySign on that machine.
3. After the build, the job waits at one approval prompt that only the maintainer can answer. When the maintainer approves, the signing
   agent receives the unsigned packages as a stash, signs each with `dotnet nuget sign`, the pinned fingerprint and a timestamp, and
   returns the signed files as a stash. The agent runs no repository code.
4. The Verify stage is unchanged: signature against the pinned fingerprint, timestamp, and content equal to the unsigned build.
5. The one-time code stays on the maintainer's phone and is typed into SimplySign Desktop on the signing machine only. No code and no
   seed is stored in Jenkins or in GitHub.
6. One setting returns the signing to the previous manual upload of a signed zip, for the case that the signing machine is not available.
7. The maintainer logs out of SimplySign after a release, so the certificate is not usable on the machine between releases.

## Alternatives

- **Keep the manual upload.** It needs no new machine, but it failed in three of three real runs, and a failure costs a tag.
- **Store the one-time-code seed in a CI secret and sign on a Windows runner or agent.** Community tools do this, and it allows unattended
  signing. The seed is then a standing credential: whoever has it can sign as the maintainer until the QR code is re-issued, and a leak
  counts as a key compromise under Certum's terms. Not chosen; it can be revisited.
- **The pipeline asks for the one-time code and logs in to SimplySign itself.** It still needs a machine with the client, and it means
  scripting the client's login window. It adds a brittle step and gains nothing over logging in by hand.
- **Sign on a Linux agent.** It needs custom code that builds the NuGet signature from a PKCS#11 or remote key. Not chosen.
- **Move the signing to GitHub Actions on a Windows runner.** It needs the seed as a secret (see above) or the same manual login on a
  machine GitHub does not provide.

## Consequences

- Positive: no upload step, no file transfer by hand, no secret added to CI, and a failure before the tag no longer uses up a version.
- Negative: the signing machine must be on, connected and logged in to SimplySign when a release is made. While SimplySign is logged
  in, any job that runs on that agent could sign with the certificate, so the label must stay restricted to the release job and the
  maintainer should log out afterwards. The agent runs in an interactive session, not as a service, because only that session sees the
  certificate.
- Follow-up: the release checklist describes the preparation (machine on, agent connected, SimplySign logged in) and the logout; the
  library's release pipeline gets the new setting and the early check.

## Compliance

- Secrets: none added. The agent's connection secret is kept in a file readable by the maintainer only on the signing machine.
- Approvals: the maintainer accepts this record as project lead and technical lead (solo mode). Certum's terms were read in version 1.4;
  the maintainer may ask Certum for confirmation in writing.
