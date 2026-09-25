"""Bump whenever ingestion turns the same .docx into a different blueprint.

Stored in every blueprint's config; a mismatch means the stored reading is stale
and can be rebuilt from the source bytes. This is deliberately not the app
version — most releases do not change ingestion, and engine fixes land between
releases.
"""
ENGINE_VERSION = 4