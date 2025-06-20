"""Simplified state schema for the Research Agent Swarm."""

from typing import Dict, Any, Optional, List
from langgraph_swarm import SwarmState
from pydantic import Field
import pandas as pd


class ResearchSwarmState(SwarmState):
    """Simple state schema for research swarm."""
    
    # PDF analysis storage
    pdf_analysis: Optional[Dict[str, Any]] = None
    current_pdf_path: Optional[str] = None
    analyzed_pdfs: List[str] = Field(default_factory=list)
    
    # Knowledge storage
    knowledge_base: Dict[str, Any] = Field(default_factory=dict)
    
    # Code generation
    generated_code: Dict[str, str] = Field(default_factory=dict)
    
    # Data preprocessing storage
    preprocessing_progress: Dict[str, Any] = Field(default_factory=dict)
    raw_data_info: Dict[str, Any] = Field(default_factory=dict)
    processed_data_paths: Dict[str, str] = Field(default_factory=dict)
    target_model: Optional[str] = None
    preprocessing_method: Optional[str] = None


def update_pdf_analysis(state: ResearchSwarmState, pdf_path: str, analysis_data: Dict[str, Any]) -> ResearchSwarmState:
    """Update state with PDF analysis results."""
    new_state = state.copy()
    new_state.pdf_analysis = analysis_data
    new_state.current_pdf_path = pdf_path
    
    if pdf_path not in new_state.analyzed_pdfs:
        new_state.analyzed_pdfs.append(pdf_path)
    
    return new_state


def update_preprocessing_progress(state: ResearchSwarmState, step: str, status: str, details: Dict[str, Any] = None) -> ResearchSwarmState:
    """Update state with preprocessing progress."""
    new_state = state.copy()
    if details is None:
        details = {}
    
    new_state.preprocessing_progress[step] = {
        "status": status,
        "details": details,
        "timestamp": str(pd.Timestamp.now())
    }
    
    return new_state


def update_raw_data_info(state: ResearchSwarmState, data_info: Dict[str, Any]) -> ResearchSwarmState:
    """Update state with raw data information."""
    new_state = state.copy()
    new_state.raw_data_info.update(data_info)
    return new_state


def set_target_model(state: ResearchSwarmState, model_name: str, preprocessing_method: str = None) -> ResearchSwarmState:
    """Set target model and preprocessing method."""
    new_state = state.copy()
    new_state.target_model = model_name
    if preprocessing_method:
        new_state.preprocessing_method = preprocessing_method
    return new_state


__all__ = ["ResearchSwarmState", "update_pdf_analysis", "update_preprocessing_progress", "update_raw_data_info", "set_target_model"]