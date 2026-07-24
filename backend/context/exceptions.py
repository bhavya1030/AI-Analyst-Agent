"""Exceptions for Conversation Context Manager."""

from __future__ import annotations


class ContextError(Exception):
    """Base error for conversation context."""


class ContextValidationError(ContextError):
    """Invalid context payload or arguments."""


class ContextNotFoundError(ContextError):
    """No context exists for the given conversation id."""


class ContextExpiredError(ContextError):
    """Context expired due to inactivity."""

    def __init__(self, conversation_id: str, message: str | None = None):
        self.conversation_id = conversation_id
        super().__init__(
            message or f"Conversation context expired: {conversation_id}"
        )


class ReferenceResolutionError(ContextError):
    """Could not resolve a linguistic reference against context."""
