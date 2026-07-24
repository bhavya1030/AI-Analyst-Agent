"""Errors for Dataset Intelligence Service."""


class IntelligenceError(Exception):
    """Base intelligence error."""


class IntelligenceValidationError(IntelligenceError):
    """Invalid path or unsupported dataset file."""


class IntelligenceReadError(IntelligenceError):
    """Failed to open or parse a dataset for structure inspection."""
