"""Evaluators that scan text for taxonomy-category violations.

Cheap tier (this package, for now) is pure regex/keyword matching, no ML
dependency, per forks.md's locked tech stack. Each scanner is single-purpose
(Fork #2: independent single-label evaluators) and reusable on both request
and response text (Phase 1.3 uses input text; Phase 2.3 reuses the same
scan() functions on output text).
"""
