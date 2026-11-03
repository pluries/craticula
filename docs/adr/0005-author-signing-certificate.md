# ADR-0005: The packages are signed with an open-source code-signing certificate held in Certum's cloud

Status: Proposed   Date: 2026-11-01
Work items: #3320   Classification: Public

Accepting this record is the maintainer's decision. It was written for readers outside the project: it names no private path or host.

## Context

- nuget.org signs every package it receives with its own certificate. A signature by the author adds the author's name and a timestamp
  the package keeps after the author's certificate expires.
- Once an author certificate is registered on a nuget.org account, nuget.org accepts only packages signed with a registered
  certificate on that account. A failed signing step then blocks the release; there is no fallback to an unsigned push.
- Since June 2023 certificate authorities issue code-signing keys only on hardware or in a cloud vault, so a downloadable key file is
  no longer sold. `dotnet nuget sign` needs a key it can read through the system or a helper.
- Craticula is Apache-2.0 and maintained by one person. The yearly cost of the certificate is capped at about 60 EUR.
- The release signs ten packages. The maintainer provides the signed packages by hand at each release.

## Decision

1. The project uses **Certum "Open Source Code Signing in the Cloud"** on SimplySign
   (https://shop.certum.eu/open-source-code-signing-on-simplysign.html), about 49 EUR a year. The key stays in Certum's cloud;
   each signing session needs a one-time code from the SimplySign phone app.
2. Packages are signed with `dotnet nuget sign` and an RFC 3161 timestamp, and checked with `dotnet nuget verify --all`.
3. Before the first real release, one probe package, `Craticula.SigningProbe`, is signed with the certificate and pushed to
   nuget.org to prove that nuget.org accepts the certificate. It is unlisted at once; nuget.org keeps the id permanently.
4. The certificate is used to sign free and open-source software only. It is not used for closed-source software unless Certum's
   terms of use say so.
5. If nuget.org rejects the certificate, the result is recorded and the budget decision is reopened before anything else is bought.

## Alternatives

- **Certum smart-card products.** The "code" item (about 25 EUR) is only an activation code for a card and reader the buyer already
  owns; the "set" (about 69 EUR) ships a card and a reader and the card cannot be returned. The key sits on a card in the signer's hand,
  not in the seller's cloud, and the set is over budget. Rejected.
- **SSL.com OV certificate with eSigner.** About 129 USD plus a plan from 180 USD a year; automatable by API, but well over the
  budget. Rejected for now.
- **Sectigo (ex-Comodo) OV through a reseller.** About 199 to 226 USD a year, sometimes with a hardware token. Over budget. Rejected.
- **Azure Artifact Signing.** About 9.99 USD a month, signs from CI without a stored secret; eligibility depends on the applicant's
  country and nuget.org's acceptance of its short-lived certificates is unconfirmed. Not chosen.
- **SignPath Foundation.** Free signing of open-source projects in CI, but the publisher on the signature is the Foundation, and the
  registration of its certificate on nuget.org and the fit with the project's build system were not verified. Not chosen; it can be
  revisited.
- **No author certificate.** The packages stay signed by nuget.org and carry a build attestation, but show no author name. Rejected
  by the project's goal of a release whose packages carry the author's signature.

## Consequences

- Positive: the packages carry the author's signature and a timestamp; the cost stays inside the budget; the key is never a file in
  the repository or on a build agent.
- Negative: each signing session needs a person with a phone, so the release cannot be fully automated; the certificate is issued to
  an individual, allows 5000 signatures a month and is for open-source use only; its validity period and renewal date are read from
  the order and tracked by a reminder 60 days before expiry; registering the certificate makes nuget.org refuse unsigned pushes on the
  account; the probe id stays on nuget.org permanently.
- The TypeScript, Python and Go ports do not use this certificate: PyPI and the other registries use keyless attestations tied to the
  publishing workflow.
- Follow-up: the release checklist records the certificate's fingerprint, expiry and the probe's result; a later change may replace the
  certificate if the probe fails or the project signs closed-source software.

## Evidence

On 2026-11-01 the three Certum product pages were read (prices, key storage, requirements, stock: the cloud and "code" pages showed
"out of stock"). Microsoft's trusted-CA list (the CCADB export of that day, 550 rows) shows the Certum roots Certum CA, Certum EC-384 CA,
Certum Trusted Network CA, Certum Trusted Network CA 2 and Certum Trusted Root CA as included with the Code Signing purpose. Which root
the issued certificate chains to is not known until it is issued, and nuget.org's acceptance is unverified: the probe tests it.
The same five roots are in the .NET SDK's own code-signing trust bundle (313 roots, SDK 10.0.114), so a local `dotnet nuget verify` can trust a
Certum chain; the oldest of them, Certum CA, expires on 2027-06-11.
Prices come from public pages and resellers, none is a quote.

## Compliance

- No key, certificate file, one-time code or personal document is stored in the repository, a log or an artifact.
- No personal data is recorded by this decision; the certificate's subject will carry the maintainer's name and "Open Source Developer".
- Third-party service: Certum's SimplySign (the signing service) and nuget.org's certificate registration. The maintainer approves both
  by accepting this record.
