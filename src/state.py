"""Enhanced state schema for the Research Agent Swarm with workflow orchestration."""

from typing import Dict, Any, Optional, List, Literal
from langgraph_swarm import SwarmState
from pydantic import Field, BaseModel
from datetime import datetime
from enum import Enum
import pandas as pd


class AgentStatus(str, Enum):
    """Status of individual agents."""
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    WAITING = "waiting"

class WorkflowStatus(str, Enum):
    """Status of workflow steps."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class WorkflowStep(BaseModel):
    """Individual workflow step with tracking."""
    name: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    agent: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

class HandoffRecord(BaseModel):
    """Record of agent handoffs."""
    from_agent: str
    to_agent: str
    reason: str
    timestamp: datetime
    context: Dict[str, Any] = Field(default_factory=dict)

class ErrorRecord(BaseModel):
    """Error tracking record."""
    agent: str
    error_type: str
    message: str
    timestamp: datetime
    context: Dict[str, Any] = Field(default_factory=dict)

class ServerStatus(BaseModel):
    """MCP server status tracking."""
    name: str
    status: Literal["connected", "disconnected", "error"]
    last_check: datetime
    tools: List[str] = Field(default_factory=list)

class AutoDRP_state(SwarmState):
    """Enhanced state schema for research swarm with workflow orchestration."""
    
    # Core data fields (existing)
    pdf_analysis: Optional[Dict[str, Any]] = None
    current_pdf_path: Optional[str] = None
    analyzed_pdfs: List[str] = Field(default_factory=list)
    knowledge_base: Dict[str, Any] = Field(default_factory=dict)
    generated_code: Dict[str, str] = Field(default_factory=dict)
    preprocessing_progress: Dict[str, Any] = Field(default_factory=dict)
    raw_data_info: Dict[str, Any] = Field(default_factory=dict)
    processed_data_paths: Dict[str, str] = Field(default_factory=dict)
    target_model: Optional[str] = None
    preprocessing_method: Optional[str] = None
    
    # Enhanced workflow orchestration
    current_workflow: Optional[str] = None
    workflow_steps: List[WorkflowStep] = Field(default_factory=list)
    
    # Agent coordination
    active_agents: Dict[str, AgentStatus] = Field(default_factory=dict)
    handoff_history: List[HandoffRecord] = Field(default_factory=list)
    
    # Error management
    error_stack: List[ErrorRecord] = Field(default_factory=list)
    retry_counts: Dict[str, int] = Field(default_factory=dict)
    
    # Tool integration
    tool_results: Dict[str, Any] = Field(default_factory=dict)
    mcp_server_status: Dict[str, ServerStatus] = Field(default_factory=dict)


class StateManager:
    """Centralized state management with workflow orchestration."""
    
    @staticmethod
    def update_pdf_analysis(state: AutoDRP_state, pdf_path: str, analysis_data: Dict[str, Any], agent: str = "analyzing") -> AutoDRP_state:
        """Update state with PDF analysis results."""
        new_state = state.copy()
        new_state.pdf_analysis = analysis_data
        new_state.current_pdf_path = pdf_path
        
        if pdf_path not in new_state.analyzed_pdfs:
            new_state.analyzed_pdfs.append(pdf_path)
        
        return new_state
    
    @staticmethod
    def update_preprocessing_progress(state: AutoDRP_state, step: str, status: str, details: Dict[str, Any] = None, agent: str = "data") -> AutoDRP_state:
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
    
    @staticmethod
    def update_raw_data_info(state: AutoDRP_state, data_info: Dict[str, Any], agent: str = "data") -> AutoDRP_state:
        """Update state with raw data information."""
        new_state = state.copy()
        new_state.raw_data_info.update(data_info)
        return new_state
    
    @staticmethod
    def set_target_model(state: AutoDRP_state, model_name: str, preprocessing_method: str = None, agent: str = "env") -> AutoDRP_state:
        """Set target model and preprocessing method."""
        new_state = state.copy()
        new_state.target_model = model_name
        if preprocessing_method:
            new_state.preprocessing_method = preprocessing_method
        return new_state
    
    @staticmethod
    def start_workflow(state: AutoDRP_state, workflow_name: str, steps: List[str]) -> AutoDRP_state:
        """Initialize a new workflow with steps."""
        workflow_steps = [WorkflowStep(name=step) for step in steps]
        new_state = state.copy()
        new_state.current_workflow = workflow_name
        new_state.workflow_steps = workflow_steps
        return new_state
    
    @staticmethod
    def update_workflow_step(state: AutoDRP_state, step_name: str, status: WorkflowStatus, 
                           agent: Optional[str] = None, error: Optional[str] = None) -> AutoDRP_state:
        """Update workflow step status."""
        new_state = state.copy()
        updated_steps = []
        
        for step in new_state.workflow_steps:
            if step.name == step_name:
                step_dict = step.model_dump()
                step_dict["status"] = status
                if agent:
                    step_dict["agent"] = agent
                if status == WorkflowStatus.IN_PROGRESS and not step.started_at:
                    step_dict["started_at"] = datetime.now()
                elif status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]:
                    step_dict["completed_at"] = datetime.now()
                if error:
                    step_dict["error"] = error
                updated_steps.append(WorkflowStep(**step_dict))
            else:
                updated_steps.append(step)
        
        new_state.workflow_steps = updated_steps
        return new_state
    
    @staticmethod
    def record_handoff(state: AutoDRP_state, from_agent: str, to_agent: str, 
                      reason: str, context: Optional[Dict[str, Any]] = None) -> AutoDRP_state:
        """Record agent handoff."""
        handoff = HandoffRecord(
            from_agent=from_agent,
            to_agent=to_agent,
            reason=reason,
            timestamp=datetime.now(),
            context=context or {}
        )
        new_state = state.copy()
        new_state.handoff_history = new_state.handoff_history + [handoff]
        return new_state
    
    @staticmethod
    def update_agent_status(state: AutoDRP_state, agent: str, status: AgentStatus) -> AutoDRP_state:
        """Update agent status."""
        new_state = state.copy()
        new_agents = new_state.active_agents.copy()
        new_agents[agent] = status
        new_state.active_agents = new_agents
        return new_state
    
    @staticmethod
    def record_error(state: AutoDRP_state, agent: str, error_type: str, 
                    message: str, context: Optional[Dict[str, Any]] = None) -> AutoDRP_state:
        """Record error in state."""
        error_record = ErrorRecord(
            agent=agent,
            error_type=error_type,
            message=message,
            timestamp=datetime.now(),
            context=context or {}
        )
        new_state = state.copy()
        new_state.error_stack = new_state.error_stack + [error_record]
        return new_state
    
    @staticmethod
    def cache_tool_result(state: AutoDRP_state, tool_name: str, result: Any) -> AutoDRP_state:
        """Cache tool result."""
        new_state = state.copy()
        new_results = new_state.tool_results.copy()
        new_results[tool_name] = result
        new_state.tool_results = new_results
        return new_state
    
    @staticmethod
    def update_mcp_server_status(state: AutoDRP_state, server_name: str, 
                                status: Literal["connected", "disconnected", "error"],
                                tools: Optional[List[str]] = None) -> AutoDRP_state:
        """Update MCP server status."""
        server_status = ServerStatus(
            name=server_name,
            status=status,
            last_check=datetime.now(),
            tools=tools or []
        )
        new_state = state.copy()
        new_status = new_state.mcp_server_status.copy()
        new_status[server_name] = server_status
        new_state.mcp_server_status = new_status
        return new_state

# Legacy function compatibility
def update_pdf_analysis(state: AutoDRP_state, pdf_path: str, analysis_data: Dict[str, Any]) -> AutoDRP_state:
    return StateManager.update_pdf_analysis(state, pdf_path, analysis_data)

def update_preprocessing_progress(state: AutoDRP_state, step: str, status: str, details: Dict[str, Any] = None) -> AutoDRP_state:
    return StateManager.update_preprocessing_progress(state, step, status, details)

def update_raw_data_info(state: AutoDRP_state, data_info: Dict[str, Any]) -> AutoDRP_state:
    return StateManager.update_raw_data_info(state, data_info)

def set_target_model(state: AutoDRP_state, model_name: str, preprocessing_method: str = None) -> AutoDRP_state:
    return StateManager.set_target_model(state, model_name, preprocessing_method)


__all__ = [
    "AutoDRP_state", "StateManager",
    "AgentStatus", "WorkflowStatus", "WorkflowStep", "HandoffRecord", "ErrorRecord", "ServerStatus",
    "update_pdf_analysis", "update_preprocessing_progress", "update_raw_data_info", "set_target_model"
]