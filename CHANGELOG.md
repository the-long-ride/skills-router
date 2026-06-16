# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.5] - 2026-06-16

### Added
- Added global `-v` and `--version` CLI flags.
- Added decorated CLI help output highlighting for `usage` and section headers.
- Added manual release workflow input to allow publish/release jobs from
  `workflow_dispatch` when explicitly enabled on a release tag.

### Changed
- Expanded help regression coverage so every registered command must appear in
  `skills-router -h`.
- Replaced machine-specific local setup paths in the integration guideline with
  workspace-neutral examples.
- Removed the legacy source rename guard job from CI.

## [0.0.4] - 2026-06-15

### Added
- Added `connect --check` to verify local MCP tool availability and managed
  bridge file presence for AI-agent hosts.
- Added `connect --apply` to write each host's recommended bridge artifact with
  one command.
- Added expanded CLI help coverage with a dedicated `help` subcommand and
  command-specific usage output.

### Changed
- Simplified `connect` usage to accept positional agent targets such as
  `skills-router connect codex --apply --check`.
- Centralized Python package versioning in `skills_router._version` and made
  setuptools read package version from that single source.
- Replaced hard-coded README version badges with dynamic PyPI version badges.

## [0.0.3] - 2026-06-11

### Added
- Added PyPI publishing to the tag release workflow using GitHub OIDC trusted publishing.
- Added `codex-ide` as a first-class target for the OpenAI Codex IDE extension.
- Added `connect --write-skill` to inject a managed Skills Router `SKILL.md`
  into the target agent skill folder.
- Added workspace `.codex/skills/skills-router/SKILL.md` bridge instructions for
  Codex IDE skill discovery.

### Changed
- Pinned the npm wrapper bootstrap install to the matching `skills-router` PyPI version.
- Updated the npm package README to explain the wrapper first, then include the full project README.
- Updated bridge prompts to treat both `/skills-router ...` and plain
  `skills-router ...` as Skills Router requests for IDEs that intercept slash
  input.
- Updated README and integration guidelines for Codex IDE setup and managed
  skill-file injection.

## [0.0.2] - 2026-06-06

### Added
- Added one-time all-agent skill installs with target-aware route metadata.
- Added bridge profiles for Antigravity, Cursor, Windsurf, and related agent targets.
- Added source-link analysis for npm and GitHub packages with conservative inferred manifest drafts.
- Added router status reporting for data paths, configured skill paths, and route counts.
- Added agent bridge setup output through `connect`, including MCP config and target instructions.

### Changed
- Tightened route lookup so custom agent target lists are enforced when a host target is provided.
- Hardened state writes on Windows test and runtime paths.
- Expanded dry-run support across write-capable CLI and MCP commands.
- Documented local editable installs, virtualenv setup, and source-based agent connection flows.

## [0.0.1] - 2026-05-27

### Added
- Initial project release of `skills-router` at v0.0.1.
- NPM wrapper project structure inside `skills-router-npx/` for seamless `npx` execution.
- Added type validation, boundary verification, and exception safety to orchestrator's decision callback handler (`_get_decision`) to fail-closed safely to cancel/no-op on error.
- Integration tests in `tests/test_orchestrator.py` covering callback safety guards.
- Comprehensive publishing and integration guidelines in `GUIDELINE.md`.

### Changed
- Replaced terminology referencing "Workgroup" and "WG" to "Workspace/Global" throughout docstrings, CLI, comments, and diagrams.
- Shortened and polished the main `README.md` to present key features, installation, quick usage, and roadmap, linking to `GUIDELINE.md` for deep details.
- Updated project license metadata in `pyproject.toml` and `package.json` to GPLv3.
