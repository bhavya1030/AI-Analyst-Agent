"""Errors for Dataset Learning Service."""


class LearningError(Exception):
    """Base learning error."""


class LearningValidationError(LearningError):
    """Invalid or incomplete learning inputs."""


class LearningRegistryError(LearningError):
    """Registry write/update failed."""
