"""Research Agent Package - Simplified exports."""

from .state import ResearchSwarmState, update_pdf_analysis
from .utils import PDFAnalyzer, get_pdf_analyzer
from .mcp import MCPManager

__all__ = [
    "ResearchSwarmState",
    "update_pdf_analysis", 
    "PDFAnalyzer",
    "get_pdf_analyzer",
    "MCPManager"
]