class AgentMaxIterationsExceeded(Exception):
    """Raised when the agent exceeds the maximum number of iterations."""

    pass


class AgentResponseError(Exception):
    """The model returned no usable answer."""
