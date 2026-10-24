SHELL := /bin/sh
UV ?= uv
PYTHON := $(CURDIR)/.venv/bin/python
export UV_CACHE_DIR := $(CURDIR)/.cache/uv
export UV_PYTHON_DOWNLOADS := never
export UV_NO_CONFIG := true
export TMPDIR := $(CURDIR)/.cache/tmp
export NPM_CONFIG_CACHE := $(CURDIR)/.cache/npm
export NPM_CONFIG_USERCONFIG := /dev/null
export NPM_CONFIG_GLOBALCONFIG := $(CURDIR)/.cache/npm-global-empty
export NPM_CONFIG_REGISTRY := https://registry.npmjs.org/
export NPM_CONFIG_IGNORE_SCRIPTS := true
export NPM_CONFIG_AUDIT := false
export NPM_CONFIG_FUND := false

.PHONY: setup preflight quick test lint typecheck web-dev web-build serve data data-offline data-correction e2e all probe evidence prepare-web

preflight:
	@mkdir -p .cache/tmp .cache/npm .cache/uv
	@touch .cache/npm-global-empty
	@node scripts/check-node.mjs
	@$(UV) python find 3.11 --no-python-downloads

setup: preflight
	$(UV) sync --frozen --python 3.11 --no-python-downloads
	cd web && npm ci --ignore-scripts --no-audit --no-fund

quick:
	$(PYTHON) -m macrolab quick

test:
	@mkdir -p runs/checks
	$(PYTHON) -m pytest --junitxml=runs/checks/pytest.xml
	cd web && npm test

lint:
	$(PYTHON) -m ruff check src tests scripts
	$(PYTHON) -m ruff format --check src tests scripts
	cd web && npm run lint

typecheck:
	$(PYTHON) -m mypy
	cd web && npm run typecheck

web-dev: prepare-web
	cd web && npm run dev -- --host 127.0.0.1

web-build: prepare-web
	cd web && npm run build

probe:
	$(PYTHON) -m macrolab.data.sources.probe

evidence:
	$(PYTHON) scripts/g0_evidence.py

# A named snapshot always replays archived bytes without network requests.
data:
	$(PYTHON) -m macrolab.data.pipeline $(if $(SNAPSHOT),--offline --snapshot $(SNAPSHOT),)

data-offline:
	@test -n "$(SNAPSHOT)" || (echo "Provide SNAPSHOT=<id> for offline reconstruction."; exit 2)
	$(PYTHON) -m macrolab.data.pipeline --offline --snapshot $(SNAPSHOT)

# Refresh only CPI, core CPI, PPI and CLI; preserve the accepted parent panel.
data-correction:
	$(PYTHON) -m macrolab.data.correction $(if $(SNAPSHOT),--offline --snapshot $(SNAPSHOT),)

serve:
	$(PYTHON) -m macrolab.api

e2e:
	$(PYTHON) scripts/g3_e2e.py

all: setup quick test lint typecheck web-build

# Uses the already-approved, checksum-verified local runtime cache; never downloads.
.PHONY: runtime-build runtime-check
runtime-build:
	$(PYTHON) scripts/build_runtime_assets.py

runtime-check: runtime-build
	$(PYTHON) scripts/g2_browser_fixture.py --verify-exports
	node scripts/g2_browser_parity.mjs

# Local review preparation never downloads source data or runtime binaries.
prepare-web:
	$(PYTHON) scripts/g3_prepare.py

# Separate local publication-readiness candidate; no fetch, push or deployment.
P1_SOURCES ?= cleared
P1_BASE_PATH ?= /macrolab/
.PHONY: p1-prepare p1-build p2-prepare p2-build static-build
p1-prepare:
	$(PYTHON) scripts/p1_prepare.py --sources $(P1_SOURCES) --base-path $(P1_BASE_PATH)

p1-build:
	$(PYTHON) scripts/p1_prepare.py --sources $(P1_SOURCES) --base-path $(P1_BASE_PATH) --build

p2-prepare:
	$(PYTHON) scripts/p1_prepare.py --candidate p2 --base-path $(P1_BASE_PATH)

p2-build:
	$(PYTHON) scripts/p1_prepare.py --candidate p2 --base-path $(P1_BASE_PATH) --build

static-build: g16-build

# Explicit v1 preparation; never changes the frozen P2/P3.1 artifacts or current pointer.
.PHONY: refresh g5-prepare g5-build g6-build regress-v0 test-v1
refresh:
	$(PYTHON) scripts/refresh.py $(if $(filter 1,$(DRY_RUN)),--dry-run,) $(if $(filter 1,$(RESUME_COMPARISON)),--resume-comparison,) $(if $(SNAPSHOT),--snapshot $(SNAPSHOT),) $(if $(PREVIOUS),--previous $(PREVIOUS),)

g5-prepare:
	$(PYTHON) scripts/g5_prepare.py

g5-build:
	$(PYTHON) scripts/g5_prepare.py --build

g6-build:
	$(PYTHON) scripts/g6_prepare.py --build

regress-v0:
	$(PYTHON) scripts/regress_v0.py --output runs/g9 --allow-version-change
	node web/scripts/g9-v0.mjs

test-v1:
	$(PYTHON) -m pytest tests/data/test_v1_sources.py tests/data/test_refresh.py tests/v1
	cd web && npm test -- tests/png-export.test.ts

# G7 writes a separate local candidate and never changes the frozen releases.
g7-build:
	$(PYTHON) scripts/g7_prepare.py --build

.PHONY: g71-build
g71-build:
	$(PYTHON) scripts/g71_prepare.py --build

.PHONY: g8-build
g8-build:
	$(PYTHON) scripts/g8_prepare.py --build

.PHONY: g9-build
g9-build:
	$(PYTHON) scripts/g9_prepare.py --build $(if $(SNAPSHOT),--snapshot $(SNAPSHOT),)

.PHONY: g10-build
g10-build:
	$(PYTHON) scripts/g10_prepare.py --build

# Local model gate; uses accepted bytes and never publishes or refreshes data.
.PHONY: g11-build test-panels
g11-build:
	$(PYTHON) scripts/g11_prepare.py --build

test-panels:
	$(PYTHON) -m pytest tests/v2/test_panel.py
	cd web && npm test -- tests/panel.test.tsx

.PHONY: g12-build
g12-build:
	$(PYTHON) scripts/g12_prepare.py --build

.PHONY: g13-build
g13-build:
	$(PYTHON) scripts/g13_prepare.py --build

.PHONY: g14-build
g14-build:
	$(PYTHON) scripts/g14_prepare.py --build

.PHONY: g15-build
g15-build:
	$(PYTHON) scripts/g15_prepare.py

.PHONY: g16-build
g16-build:
	$(PYTHON) scripts/g16_prepare.py --build $(if $(SNAPSHOT),--snapshot $(SNAPSHOT),)
