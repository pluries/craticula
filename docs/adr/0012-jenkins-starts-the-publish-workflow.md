# ADR-0012: The release pipeline starts the publish workflow and waits for it

Status: Accepted   Date: 2026-11-10
Work items: #3776   Classification: Public

The maintainer accepted this record on 2026-11-10 as project lead and technical lead (solo mode), choosing "start and wait, the maintainer still approves the environment on GitHub".
It amends ADR-0010, which left the start of the workflow to the maintainer. It names no private path or host.

## Context

- ADR-0010 has the release pipeline stage the signed packages in a draft GitHub release and then pause. The maintainer runs the workflow `nuget-publish` on GitHub, approves its environment `nuget`, and confirms in Jenkins.
- The first release (2026-11-10) showed how many hand-offs that is: open GitHub, find the workflow, enter the tag, start it, approve, watch it, go back to Jenkins and confirm. A mistake costs a version or a confusing failed run (two runs of the old release workflow were started by mistake the same day).
- ADR-0010 considered letting Jenkins start the workflow and left it out, because the Jenkins token would then be allowed to run workflows and the approval of the environment would be the only gate.

## Decision

1. After staging, the release pipeline starts the workflow `nuget-publish` for the tag through the GitHub API (`workflow_dispatch` on `main`), finds the run it started by its title (the workflow's `run-name` names the tag), and waits for it for at most a configured time (default 90 minutes). It continues when the run has succeeded and stops, naming the run, when the run fails, is cancelled or does not finish in time.
2. **The pipeline never approves the environment.** The maintainer approves `nuget` on GitHub, as before. Nothing in the pipeline calls the endpoint that reviews deployments, and the token has no Deployments permission, which is what that endpoint needs. A fine-grained token always belongs to a user, here the maintainer, who is also the environment's reviewer, so the separation rests on that missing permission and on the pipeline's code, not on a different identity. "Prevent self-review" must stay off on `nuget`, because the run is started under the maintainer's identity.
3. The GitHub token of the release job gets two more permissions on the one repository: Actions read and write. It keeps its contents permission and its scope of one repository, and it keeps **no** Deployments permission.
4. One setting returns to the manual mode of ADR-0010: the pipeline tells the maintainer which workflow to run and pauses until the maintainer confirms.
5. Everything else in ADR-0010 stays: the three jobs of the workflow, the checks before the push, the temporary key from Trusted Publishing, and the check that all ten packages are on nuget.org before the GitHub release becomes public.

## Alternatives

- **Keep the manual start.** Simplest and the smallest token; costs the hand-offs described above.
- **Start the workflow and also approve the environment from Jenkins, after the maintainer's approval in Jenkins.** Zero clicks on GitHub, but it needs the Deployments permission on the token, so the approval on GitHub would no longer be a gate apart from Jenkins. Not chosen.
- **Move the whole release into GitHub Actions.** The signing needs the maintainer's machine and phone; see ADR-0010 and ADR-0011.

## Consequences

- Positive: no manual start of the workflow, no wrong tag typed on GitHub, no confirmation to click in Jenkins, and a clear stop with the run's address when the workflow fails.
- Negative: the Jenkins token can now start workflows in the public repository, and read their runs. A leaked token or a changed release pipeline could start any workflow that accepts a `workflow_dispatch`. What stays in the way: the token is limited to one repository, the release job cannot be replayed with a changed script by anyone but the maintainer, the workflows run from `main` only, and `nuget-publish` needs the maintainer's approval of its environment before it can push anything. The token's rotation reminder stays at 12 months.
- The pipeline holds an agent for the whole wait (at most the configured time, 90 minutes by default), where the earlier waits held none. A single short failure of the GitHub API during the wait is retried (up to five in a row); a failed run, a cancelled run, a refusal or a wait that runs out stops the release with the run's address, and the release is then finished by hand because the job cannot resume.
- Follow-up: the maintainer widens the token's permissions before the next release (Actions read and write, Deployments none); the runbook says so.

## Compliance

- Secrets: no new secret. The existing token credential gets two more repository permissions.
- Approvals: accepted by the maintainer as project lead and technical lead (solo mode).
