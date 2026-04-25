# Project Mandates: The Spillover Engine

## Source Control & Workflow
- **Conventional Commits**: All commits MUST follow the [Conventional Commits](https://www.conventionalcommits.org/) specification (e.g., `feat:`, `fix:`, `docs:`, `chore:`).
- **Branching Strategy**: Assume a PR-based workflow. New features or fixes should be developed on feature branches (e.g., `feat/feature-name`) before merging into the main branch.
- **Commit Granularity**: Keep commits surgical and focused on a single logical change.

## Architecture & Data
- **Python/Pandas**: Mandatory for data processing to handle messy government Excel/CSV headers and 'D' disclosure strings.
- **Dependent Multiplier**: Always use a 2.2x multiplier for dependents on all primary I-140 and I-485 counts.
- **INA Logic**: Adhere to INA 201/203 spillover flow and the '75-Country Freeze' redistribution logic as defined in the core engine.
