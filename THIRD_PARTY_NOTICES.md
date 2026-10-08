# Dependency and source attribution

Runtime, tests and review scripts use only the Python standard library. There are no pip packages, vendored upstream code or model SDKs. Project code, documentation and self-authored fictional fixtures use the MIT license in LICENSE. No runtime was downloaded or redistributed by this local project phase; prepared CI may fetch its interpreter using setup-python.

Verified baseline on this HP: CPython 3.11.9, SQLite 3.45.1 (`py -3.11`). PATH `python` selects CPython 3.12.7 instead; it is not the baseline command.

- [CPython v3.11.9 license](https://raw.githubusercontent.com/python/cpython/v3.11.9/LICENSE): Python Software Foundation License Version 2, historical/incorporated notices and documentation-example terms. The interpreter is a prerequisite, not redistributed by this project.
- [SQLite copyright](https://www.sqlite.org/copyright.html): the deliverable SQLite library is dedicated to the public domain. SQLite is supplied by the installed interpreter; its actual version is recorded in evidence.
- [Python 3.11.9 release](https://www.python.org/downloads/release/python-3119/) and [SQLite 3.45.1 release](https://www.sqlite.org/releaselog/3_45_1.html): version/artifact records read during planning.

Research-only references: [OPA agent tool calling](https://www.openpolicyagent.org/docs/agent-tool-calling), [Cedar authorization](https://docs.cedarpolicy.com/auth/authorization.html), [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [OWASP Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/), and [MCP 2025-11-25 tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools). They inform the design; no code or documentation passages are copied, and no compatibility with their policy/protocol formats is claimed. Retrieval date: 2026-10-07. Full research/pin evidence is in PLAN.md.

Prepared CI-only dependencies (no hosted run observed):

- actions/checkout v7.0.1, commit `3d3c42e5aac5ba805825da76410c181273ba90b1`: [MIT license at the pinned commit](https://raw.githubusercontent.com/actions/checkout/3d3c42e5aac5ba805825da76410c181273ba90b1/LICENSE).
- actions/setup-python v7.0.0, commit `5fda3b95a4ea91299a34e894583c3862153e4b97`: [MIT license at the pinned commit](https://raw.githubusercontent.com/actions/setup-python/5fda3b95a4ea91299a34e894583c3862153e4b97/LICENSE).

Both action declarations use Node 24 in GitHub's action runtime; Node is not a project application dependency. Tags/commits were verified on 2026-10-07; pinned action declarations/licenses were actually read on 2026-10-08. The workflow references these upstream actions without vendoring their code. Python is pinned to 3.11.9, while hosted runner images/bundled SQLite are platform supplied and recorded at execution. [Verification notes](docs/verification.md) state availability evidence and unexecuted checks. License notices for prerequisites remain upstream; the MIT project license does not relicense CPython, SQLite or the actions.
