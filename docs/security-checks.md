# Automated security checks

The [Security workflow](../.github/workflows/security.yml) runs for pull requests
and pushes to `dev` and `main`, every Tuesday at 03:17 UTC, and on manual dispatch.
Scheduled runs use the repository's default branch. The jobs need no application
keys or database. Checkout credentials are not retained, and the token has only
read access to repository contents.

Scanner releases are pinned to Bandit 1.9.4 and pip-audit 2.10.1. Update those
versions in the workflow and local commands together when reviewing new releases.
Advisory data is still fetched on each run.

| Check | Scope | Fails when |
| --- | --- | --- |
| Bandit | Python source in `backend/app` | A medium or high severity finding is reported. |
| pip-audit | A fresh backend runtime install, including transitive dependencies and the auditor's dependencies | A known vulnerability is reported or dependency collection fails. |
| npm audit | Both application lockfiles, including build and migration tools | A high or critical advisory is reported, or the registry cannot complete the audit. |

The Python project itself is editable and unpublished. The job writes
`pip freeze --exclude-editable` to a temporary requirements file and audits those
exact installed versions with `--no-deps --disable-pip`. This excludes only the
local editable package; its installed dependencies are still audited. The job
prints that file because the backend uses version ranges, without a Python
lockfile. This checks a fresh install;
audit the deployed environment separately to check its exact versions. Optional
Grounding DINO dependencies (`.[grounding]`) and marketing production scripts
are outside these jobs.

The JavaScript checks read committed lockfiles without installing packages or
running their lifecycle scripts. They include development dependencies: Vite
builds the deployed frontend, and Prisma runs database migrations. A production
only scan would omit Prisma entirely because it is a development dependency.

Bandit's two `B608` exceptions in the precompute script apply only to migration
file generation: column names are fixed, string values escape single quotes,
and the generated transaction sets `standard_conforming_strings` explicitly.
The script does not execute those constructed statements. A PostgreSQL
regression checks adversarial quotes and backslashes survive an export and
import as data. No scanner-wide rules are disabled.

To reproduce locally from the repository root:

```sh
cd backend
python3 -m venv /tmp/linguini-security-env
/tmp/linguini-security-env/bin/python -m pip install --upgrade pip
/tmp/linguini-security-env/bin/python -m pip install -e . bandit==1.9.4 pip-audit==2.10.1
/tmp/linguini-security-env/bin/python -m bandit -r app -ll
/tmp/linguini-security-env/bin/python -m pip freeze --exclude-editable > /tmp/linguini-security-requirements.txt
/tmp/linguini-security-env/bin/python -m pip_audit -r /tmp/linguini-security-requirements.txt --strict --no-deps --disable-pip
```

Run `npm audit --package-lock-only --audit-level=high` once in `frontend/` and once
in `backend/`. Advisory checks need network access. A failed registry request is
an incomplete check, not evidence that no vulnerabilities exist.

Review each finding before changing dependencies. Do not use forced automatic
upgrades or blanket suppressions to make a job pass. These checks detect known
advisories and selected code patterns; ownership, authentication, payment logic,
private media, and deployment configuration still need adversarial tests and
manual review. Branch protection must require these jobs if merges should be
blocked by a failed scan.

Tool references: [Bandit CLI](https://bandit.readthedocs.io/en/latest/man/bandit.html),
[pip-audit](https://github.com/pypa/pip-audit), and
[npm audit](https://docs.npmjs.com/cli/v11/commands/npm-audit/).
