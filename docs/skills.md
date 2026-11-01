# Repository skills

The canonical home for all repository skills is [`.agents/skills/`](../.agents/skills/).
Keep each skill's instructions, scripts, references and assets together there.
Repository-wide workflow rules remain in [AGENTS.md](../AGENTS.md), with UI-specific
rules in [frontend/AGENTS.md](../frontend/AGENTS.md).

## Skills used for Linguini development

| Skill | Purpose |
| --- | --- |
| [linguini-live-ui-testing](../.agents/skills/linguini-live-ui-testing/SKILL.md) | Check the intended local environment and exercise saved session flows |
| [impeccable](../.agents/skills/impeccable/SKILL.md) | UI design, accessibility, review and visual refinement |
| [stripe-best-practices](../.agents/skills/stripe-best-practices/SKILL.md) | Stripe integration and subscription guidance |
| [stripe-docs](../.agents/skills/stripe-docs/SKILL.md) | Stripe documentation lookup |
| [upgrade-stripe](../.agents/skills/upgrade-stripe/SKILL.md) | Stripe API and SDK upgrades |

## Additional bundled skills

These vendor workflows are available for an explicit task. Their presence does
not mean Linguini uses the associated product or service.

| Skill | Purpose |
| --- | --- |
| [connect-recommend](../.agents/skills/connect-recommend/SKILL.md) | Stripe Connect platform and charge-pattern guidance |
| [connect-required-verification-information](../.agents/skills/connect-required-verification-information/SKILL.md) | Connected-account verification requirements |
| [metronome](../.agents/skills/metronome/SKILL.md) | Usage-based billing integrations |
| [stripe-apps](../.agents/skills/stripe-apps/SKILL.md) | Stripe Dashboard apps and extensions |
| [stripe-directory](../.agents/skills/stripe-directory/SKILL.md) | External provider discovery through Stripe Directory |
| [stripe-pay](../.agents/skills/stripe-pay/SKILL.md) | Explicitly requested Stripe business payments |
| [stripe-projects](../.agents/skills/stripe-projects/SKILL.md) | Explicitly requested infrastructure provisioning |

## Compatibility and maintenance

`.claude/skills` is a relative symlink to `.agents/skills`.
`frontend/impeccable` is a relative symlink to the canonical Impeccable skill.
These preserve existing discovery and command paths without maintaining duplicate
skill bodies or binaries. `.claude/agents/` contains client-specific reviewer and
worker definitions rather than another copy of the skill. The existing Codex
hooks already point at `.agents/skills/impeccable`.

On Windows, check out the repository with Git symlink support enabled; otherwise
use the canonical `.agents/skills` paths directly. The application and production
build do not depend on these tooling paths.

Edit the canonical file, verify its referenced files and scripts, and commit the
change through the normal `dev` PR workflow. Keep third-party licences and asset
provenance. Do not copy credentials, local sessions or generated test data into a
skill. Adding or moving a skill must also update this index.
