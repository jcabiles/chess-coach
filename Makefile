# One check command for every agent and person: the same lint and tests CI runs.
# Paths are anchored to the main checkout, so `make` behaves the same inside .worktrees/<id>
# and reuses the main checkout's virtualenv.
MAIN := $(patsubst %/,%,$(dir $(shell git rev-parse --path-format=absolute --git-common-dir)))
VENV ?= $(MAIN)/.venv
BASE ?= main

.PHONY: check lint test ticket

check: lint test

lint:
	$(VENV)/bin/ruff check

test:
	$(VENV)/bin/python -m pytest -q

# Claim a roadmap ticket: `make ticket ID=pilot-1` creates .worktrees/pilot-1 on branch
# ticket/pilot-1 from $(BASE). An existing branch means another session already claimed it.
ticket:
	@test -n "$(ID)" || { echo "usage: make ticket ID=<ticket id> [BASE=<branch>]"; exit 2; }
	@if git show-ref --verify --quiet refs/heads/ticket/$(ID); then echo "ticket $(ID) is already claimed (branch ticket/$(ID) exists)"; exit 1; fi
	git -C "$(MAIN)" worktree add -b ticket/$(ID) "$(MAIN)/.worktrees/$(ID)" $(BASE)
