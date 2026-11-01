# Project documentation

Linguini is the **CS3216 final project for Group 3**. This index links the current
application guides and the supporting project work.

| Topic | Start here |
| --- | --- |
| Product, architecture and local setup | [Root README](../README.md) |
| Frontend, routes and deployment | [Frontend README](../frontend/README.md) |
| API, database, AI configuration and tracing | [Backend README](../backend/README.md) |
| Development workflow and review rules | [AGENTS.md](../AGENTS.md) |
| UI implementation conventions | [Frontend guide](../frontend/AGENTS.md) |
| Product design and visual tokens | [Design guide](../frontend/design.md) |
| Repository skills | [Skills index](skills.md) |
| Security findings and staging checks | [Security review](SECURITY.md) (introduced in [#258](https://github.com/Learn-with-Linguini/linguini/pull/258)) |
| Static and dependency scans | [Security checks](security-checks.md) (introduced in [#258](https://github.com/Learn-with-Linguini/linguini/pull/258)) |
| Analytics events and pages | [Analytics](../ANALYTICS.md) |
| Missions, Basil and reward accounting | [Gamification policy](gamification.md) |
| Persistent private I-Spy conversations | [Friend I-Spy](friend-ispy.md) |
| Model choices and evaluation results | [Model comparison](../MODEL_COMPARISON.md) |
| Evaluation datasets and runners | [Backend evaluations](../backend/evals/README.md) |
| Launch media, pricing model and milestone records | [Marketing](../marketing/README.md) |
| Learner memory research | [Research notes](research/learner-memory.md) |

Current configuration lives in the app-level `.env.example` files and
[`backend/ai.toml`](../backend/ai.toml). Read the corresponding app guide before
running migrations, tests or generation scripts.

Marketing proposals and milestone write-ups retain their original dates and
assumptions. They are evidence of project development; they do not establish
current deployment status, pricing or feature availability. Use the source code
and current app guides for those details. Media credits, licences and model names
are retained where needed for provenance and reproducibility.
