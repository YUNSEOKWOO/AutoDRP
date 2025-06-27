"""Simplified state schema for the AutoDRP multi-agent system."""

from typing import Dict, Any, Optional
from langgraph_swarm import SwarmState
from pydantic import Field


class AutoDRP_state(SwarmState):
    """Simplified state schema for AutoDRP multi-agent system."""
    
    # Core data fields
    pdf_analysis: Optional[Dict[str, Any]] = None
    preprocessing_progress: Dict[str, Any] = Field(default_factory=dict)
    
    # Agent information storage
    current_agent_tasks: Dict[str, str] = Field(default_factory=dict)  # {agent: current_task}
    agent_results: Dict[str, Any] = Field(default_factory=dict)        # {agent: results}
    
    # Handoff information
    handoff_context: Dict[str, Any] = Field(default_factory=dict)      # Simple handoff info


class StateManager:
    """Simplified state management for AutoDRP."""
    
    @staticmethod
    def update_pdf_analysis(state, pdf_path: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update state with PDF analysis results."""
        # Simple dict-based approach for SwarmState compatibility
        if not isinstance(state, dict):
            state = {}
        
        new_state = state.copy()
        new_state['pdf_analysis'] = analysis_data
        return new_state
    
    @staticmethod
    def update_preprocessing_progress(state, step: str, status: str, details: Dict[str, Any] = None) -> Dict[str, Any]:
        """Update state with preprocessing progress."""
        if not isinstance(state, dict):
            state = {}
        
        new_state = state.copy()
        if 'preprocessing_progress' not in new_state:
            new_state['preprocessing_progress'] = {}
        
        new_state['preprocessing_progress'][step] = {
            "status": status,
            "details": details or {}
        }
        return new_state
    
    @staticmethod
    def update_agent_result(state, agent: str, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update state with agent results."""
        if not isinstance(state, dict):
            state = {}
        
        new_state = state.copy()
        if 'agent_results' not in new_state:
            new_state['agent_results'] = {}
        
        new_state['agent_results'][agent] = result_data
        return new_state
    
    @staticmethod
    def update_handoff_context(state, from_agent: str, to_agent: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Update handoff context information."""
        if not isinstance(state, dict):
            state = {}
        
        new_state = state.copy()
        if 'handoff_context' not in new_state:
            new_state['handoff_context'] = {}
        
        new_state['handoff_context'].update({
            'from_agent': from_agent,
            'to_agent': to_agent,
            'context': context
        })
        return new_state

# Legacy function compatibility
def update_pdf_analysis(state, pdf_path: str, analysis_data: Dict[str, Any]):
    return StateManager.update_pdf_analysis(state, pdf_path, analysis_data)

def update_preprocessing_progress(state, step: str, status: str, details: Dict[str, Any] = None):
    return StateManager.update_preprocessing_progress(state, step, status, details)


__all__ = [
    "AutoDRP_state", "StateManager",
    "update_pdf_analysis", "update_preprocessing_progress"
]