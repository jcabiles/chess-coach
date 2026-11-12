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

# Claim an agent ticket: `make ticket ID=<id>` creates .worktrees/<id> on branch ticket/<id>
# from $(BASE). An existing branch means another session already claimed it. Values reach the
# shell as environment variables, never as recipe text, and a missing tool folder stops the claim.
# Tool folders installed in the main checkout, linked into each ticket worktree.
LINK_DIRS := .venv

ticket: export TICKET_ID = $(ID)
ticket: export TICKET_BASE = $(BASE)
ticket: export TICKET_MAIN = $(MAIN)
ticket: export TICKET_LINKS = $(LINK_DIRS)
ticket:
	@case "$$TICKET_ID" in "") echo "usage: make ticket ID=<ticket id> [BASE=<branch>]"; exit 2 ;; -* | .* | *[!A-Za-z0-9._-]*) echo "ticket id may use only letters, digits, dot, dash and underscore"; exit 2 ;; esac; \
	case "$$TICKET_BASE" in "" | -*) echo "BASE must name a branch"; exit 2 ;; esac; \
	for d in $$TICKET_LINKS; do test -e "$$TICKET_MAIN/$$d" || { echo "not claimed: $$d is missing in the main checkout; install dependencies there first"; exit 1; }; done; \
	if git show-ref --verify --quiet "refs/heads/ticket/$$TICKET_ID"; then echo "ticket $$TICKET_ID is already claimed (branch ticket/$$TICKET_ID exists)"; exit 1; fi; \
	set -e; git -C "$$TICKET_MAIN" worktree add -b "ticket/$$TICKET_ID" "$$TICKET_MAIN/.worktrees/$$TICKET_ID" "$$TICKET_BASE"; \
	for d in $$TICKET_LINKS; do ln -s "$$TICKET_MAIN/$$d" "$$TICKET_MAIN/.worktrees/$$TICKET_ID/$$d"; done; \
	echo "claimed: $$TICKET_MAIN/.worktrees/$$TICKET_ID"
