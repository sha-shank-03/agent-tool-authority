"""Host-side mediation for structured tool calls; the host is trusted."""

from .gateway import AgentFacade, Gateway, OperatorService
from .workspace import initialize, open_workspace

__all__ = ["AgentFacade", "Gateway", "OperatorService", "initialize", "open_workspace"]
__version__ = "0.1.0"
