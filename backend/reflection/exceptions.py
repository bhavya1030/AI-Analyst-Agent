"""Exceptions for Reflection / Self-Correction Agent."""

from __future__ import annotations


class ReflectionError(Exception):
    """Base reflection error."""


class ReflectionValidationError(ReflectionError):
    """Invalid reflection input."""


class ReflectionSeverityError(ReflectionError):
    """Raised only when callers opt into hard-fail on severe issues."""
