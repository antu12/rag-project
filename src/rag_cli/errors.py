class RagError(Exception):
    """Base exception for user-facing CLI errors."""


class ConfigError(RagError):
    pass


class WorkspaceError(RagError):
    pass


class ProviderError(RagError):
    pass


class StorageError(RagError):
    pass


class IngestError(RagError):
    pass
