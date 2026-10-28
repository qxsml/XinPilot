# Modular architecture

See the [engineering overview](ENGINEERING_OVERVIEW.md) for the dependency
diagram, code map, state ownership and validation boundaries.

Project persistence, robot compilation, analysis-job identity, process transport
and renderer components have explicit modules. Existing controller imports and
saved-project fields remain compatible. Hidden Tk widgets remain adapters for
layout and established interactions; this is not a Tk-free rewrite or a new
public orchestration API. Both PyParse implementations retain their existing
source and are outside the architectural refactor.

This repository is the prepared source snapshot. Local experimental records,
development environments and build outputs are excluded. See the
[validation summary](validation-summary.md) and [publication steps](publication.md).
