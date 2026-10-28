# Dependency provenance and licensing

Application ownership/licensing has not been assigned. Existing notices in installed
packages must be retained. Registry resolutions are exact in the committed lockfiles;
no package lifecycle script runs during frontend install. No external 3D asset is used.

| Direct dependency | Provenance | Published license family |
| --- | --- | --- |
| React / React DOM | npm react, react-dom; facebook/react | MIT |
| Three.js | npm three; mrdoob/three.js | MIT |
| Vite / TypeScript | npm vite, typescript; vitejs/vite, microsoft/TypeScript | MIT / Apache-2.0 |
| Playwright / axe | npm @playwright/test, @axe-core/playwright; microsoft/playwright, dequelabs/axe-core | Apache-2.0 / MPL-2.0 (axe core); preserve package-specific notices |
| FastAPI | PyPI fastapi; fastapi/fastapi | MIT |
| Uvicorn / HTTPX | PyPI uvicorn, httpx; encode maintainers | BSD-3-Clause |
| SQLAlchemy | PyPI sqlalchemy; sqlalchemy/sqlalchemy | MIT |
| psycopg / psycopg-binary | PyPI psycopg; psycopg/psycopg | LGPL-3.0 with stated linking exception; review redistribution and bundled libpq/OpenSSL notices |
| Python / Alpine | Official Docker Library Python image, pinned manifest digest | Python PSF and distribution/package-specific licenses |
| pytest / Ruff / pip-audit | PyPI tooling; pytest-dev, astral-sh, pypa | MIT / MIT / Apache-2.0 |

Review the actual installed metadata and bundled native libraries before distributing
images commercially. This intake is not a legal approval or a new project license.
Dependency audits establish only known advisories at their execution time. The initial
pytest 9.0.2 finding was remediated to 9.0.3. Unused pip/setuptools/wheel are removed
from the runtime image; they remain development tools outside the container.

The original Debian image failed the high/critical runtime gate even after available
updates. The candidate therefore uses a separately qualified official Alpine image;
its scan result must be recorded separately. No scanner ignore or unfixed-vulnerability
filter is used to turn the failed Debian result into a pass.
