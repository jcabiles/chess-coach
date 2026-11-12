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
# from $(BASE). An existing branch means another session already claimed it.
# Tool folders installed in the main checkout, linked into each ticket worktree.
LINK_DIRS := .venv

ticket:
	@test -n "$(ID)" || { echo "usage: make ticket ID=<ticket id> [BASE=<branch>]"; exit 2; }
	@case "$(ID)" in -* | .* | *[!A-Za-z0-9._-]*) echo "ticket id may use only letters, digits, dot, dash and underscore"; exit 2 ;; esac
	@if git show-ref --verify --quiet refs/heads/ticket/$(ID); then echo "ticket $(ID) is already claimed (branch ticket/$(ID) exists)"; exit 1; fi
	git -C "$(MAIN)" worktree add -b ticket/$(ID) "$(MAIN)/.worktrees/$(ID)" $(BASE)
	@for d in $(LINK_DIRS); do test -e "$(MAIN)/$$d" && ln -s "$(MAIN)/$$d" "$(MAIN)/.worktrees/$(ID)/$$d" || echo "not linked: $$d (missing in the main checkout)"; done
