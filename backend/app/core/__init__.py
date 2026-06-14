"""Domain-agnostic core of the peer-tutor framework.

`core/domain` defines the seam (protocols + value types) that the agent loop,
governance, measures, and learner model depend on, so they no longer import a
concrete domain (e.g. `quantum/*`). A concrete domain is supplied as a
`DomainPack` and selected at runtime by the registry (see `core.domain`).
"""
