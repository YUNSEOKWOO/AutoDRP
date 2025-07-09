from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm
from typing import Dict, Any, Optional, List, Callable
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
import functools
import json
import asyncio
import os

from AutoDRP.mcp import MCPManager
from AutoDRP.state import AutoDRP_state, StateManager, update_pdf_analysis, update_preprocessing_progress
from AutoDRP.prompts import data_agent_prompt, env_agent_prompt, mcp_agent_prompt, code_agent_prompt, analyzing_prompt
from AutoDRP.utils import get_pdf_analyzer

# =============================================================================
#  CONFIGURATION
# =============================================================================

# Configure which agents to activate
# Available agents: analyzing_agent, data_agent, env_agent, mcp_agent, code_agent
ACTIVE_AGENTS = [
    # "analyzing_agent",
    "data_agent", 
    # "env_agent",
    # "mcp_agent", 
    # "code_agent"
]

# Agent metadata for dynamic creation
AGENT_METADATA = {
    "analyzing_agent": {
        "prompt": analyzing_prompt,
        "mcp_tools": ["sequential_thinking", 
                      "desktop_commander", 
                    #   "context7", 
                      "serena"],
        "special_tools": ["pdf_analyzer"],
        "description": "Research paper analysis and code inspection"
    },
    "data_agent": {
        "prompt": data_agent_prompt,
        "mcp_tools": ["sequential_thinking", 
                      "desktop_commander", 
                      "context7", 
                      "serena"
                      ],
        "description": "Custom data preprocessing pipeline creation"
    },
    "env_agent": {
        "prompt": env_agent_prompt, 
        "mcp_tools": ["sequential_thinking", 
                    #   "desktop_commander", 
                      "context7", 
                    #   "serena"
                      ],
        "description": "Docker environment and dependency management"
    },
    "mcp_agent": {
        "prompt": mcp_agent_prompt,
        "mcp_tools": ["sequential_thinking", 
                    #   "desktop_commander", 
                      "context7", 
                    #   "serena"
                      ],
        "description": "MCP server coordination and API wrapping"
    },
    "code_agent": {
        "prompt": code_agent_prompt,
        "mcp_tools": ["sequential_thinking", 
                      "desktop_commander", 
                    #   "context7", 
                    #   "serena"
                      ],
        "description": "Model execution and API communication"
    }
}

# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================

def validate_agent_config():
    """Validate the ACTIVE_AGENTS configuration."""
    if not ACTIVE_AGENTS:
        raise ValueError("At least one agent must be active")
    
    invalid_agents = [agent for agent in ACTIVE_AGENTS if agent not in AGENT_METADATA]
    if invalid_agents:
        raise ValueError(f"Invalid agent names: {invalid_agents}")
    
    return True

# =============================================================================
# DYNAMIC HANDOFF TOOL GENERATION
# =============================================================================

def create_handoff_tools():
    """Create handoff tools dynamically based on active agents."""
    handoff_tools = {}
    
    for agent_name in ACTIVE_AGENTS:
        tool_name = f"transfer_to_{agent_name}"
        description = f"Transfer the user to the {agent_name} for {AGENT_METADATA[agent_name]['description']}."
        
        handoff_tools[tool_name] = create_handoff_tool(
            agent_name=agent_name,
            description=description
        )
        
    return handoff_tools

# =============================================================================
# OPTIMIZED MCP TOOL LOADING
# =============================================================================

def get_required_mcp_tools():
    """Determine which MCP tools are needed based on active agents."""
    required_tools = set()
    
    for agent_name in ACTIVE_AGENTS:
        agent_tools = AGENT_METADATA[agent_name]["mcp_tools"]
        required_tools.update(agent_tools)
    
    return list(required_tools)

# =============================================================================
# UTILITY FUNCTIONS (FROM ORIGINAL)
# =============================================================================

def limit_output(text: str, max_length: int = 1000) -> str:
    """출력 텍스트 길이 제한으로 토큰 사용량 최적화"""
    if len(text) <= max_length:
        return text
    return text[:max_length-10] + "...[생략]"

def compress_debug_output(text: str, max_length: int = 200) -> str:
    """디버그/로그 출력만 압축 (AutoDRP_state 정보는 제외)"""
    if any(keyword in text.lower() for keyword in ['autodrp_state', 'pdf_analysis', 'preprocessing_progress', 'raw_data_info']):
        return text
    
    if len(text) > max_length:
        half_length = max_length // 2
        return f"{text[:half_length]}...[생략]...{text[-half_length:]}"
    return text

def compress_file_list(files: list, max_count: int = 3) -> str:
    """파일 리스트 압축 표시"""
    if len(files) <= max_count:
        return ", ".join(files)
    
    shown_files = files[:max_count]
    remaining_count = len(files) - max_count
    return f"{', '.join(shown_files)} ... (+{remaining_count}개 파일 더)"

def compress_error_message(error: Exception, max_length: int = 100) -> str:
    """오류 메시지 압축"""
    error_msg = str(error)
    if len(error_msg) <= max_length:
        return f"{type(error).__name__}: {error_msg}"
    
    return f"{type(error).__name__}: {error_msg[:max_length-20]}...{error_msg[-15:]}"

# =============================================================================
# SPECIAL TOOLS CREATION
# =============================================================================

def create_pdf_tools():
    """Create PDF analysis tools for analyzing_agent."""
    from langchain_core.tools import tool
    
    # Get PDF analyzer instance
    pdf_analyzer = get_pdf_analyzer()
    
    @tool
    def analyze_pdfs(query: str = "") -> str:
        """Analyze PDF documents in models directory with optional query focus."""
        try:
            pdf_files = pdf_analyzer.find_pdf_files()
            if not pdf_files:
                return "No PDF files found in models directory"
            
            results = []
            for pdf_path in pdf_files[:3]:  # Limit to 3 PDFs
                analysis = pdf_analyzer.analyze_content(pdf_path, query)
                if "error" not in analysis:
                    pdf_name = os.path.basename(pdf_path)
                    total_chunks = analysis.get('total_chunks', 0)
                    arch_score = analysis.get('content_summary', {}).get('architecture', {}).get('relevance_score', 0)
                    method_score = analysis.get('content_summary', {}).get('methodology', {}).get('relevance_score', 0)
                    
                    results.append(f"📄 {pdf_name}: {total_chunks} chunks, Architecture: {arch_score}, Methodology: {method_score}")
                else:
                    results.append(f"❌ {os.path.basename(pdf_path)}: {analysis['error']}")
            
            return "\n".join(results)
        except Exception as e:
            return f"Error analyzing PDFs: {str(e)}"
    
    @tool
    def find_pdf_files() -> str:
        """Find all available PDF files in the models directory."""
        try:
            pdf_files = pdf_analyzer.find_pdf_files()
            if not pdf_files:
                return "No PDF files found in models directory"
            
            file_list = []
            for pdf_path in pdf_files:
                file_size = os.path.getsize(pdf_path) // 1024  # KB
                file_list.append(f"📄 {os.path.basename(pdf_path)} ({file_size}KB)")
            
            return f"Found {len(pdf_files)} PDF files:\n" + "\n".join(file_list)
        except Exception as e:
            return f"Error finding PDFs: {str(e)}"
    
    @tool
    def get_pdf_summary(pdf_name: str = "") -> str:
        """Get detailed summary of a specific PDF file."""
        try:
            if not pdf_name:
                return "Please specify a PDF filename"
            
            analysis = pdf_analyzer.analyze_content(pdf_name)
            if "error" in analysis:
                return f"Error: {analysis['error']}"
            
            summary = []
            summary.append(f"📄 File: {os.path.basename(analysis['source_file'])}")
            summary.append(f"📊 Total chunks: {analysis.get('total_chunks', 0)}")
            
            content_summary = analysis.get('content_summary', {})
            for category, data in content_summary.items():
                score = data.get('relevance_score', 0)
                if score > 0:
                    summary.append(f"🔍 {category.title()}: {score} matches")
            
            sections = analysis.get('extracted_sections', [])
            if sections:
                summary.append(f"📋 Key sections: {len(sections)} found")
            
            return "\n".join(summary)
        except Exception as e:
            return f"Error getting PDF summary: {str(e)}"
    
    return [analyze_pdfs, find_pdf_files, get_pdf_summary]

# =============================================================================
# GENERIC AGENT CREATION
# =============================================================================

async def create_generic_agent(agent_name: str, tools_dict: Dict, handoff_tools: Dict):
    """Create agent dynamically based on AGENT_METADATA configuration."""
    if agent_name not in AGENT_METADATA:
        raise ValueError(f"Unknown agent: {agent_name}")
    
    metadata = AGENT_METADATA[agent_name]
    
    # Build MCP tools list from metadata
    agent_tools = []
    for tool_name in metadata["mcp_tools"]:
        agent_tools.extend(tools_dict.get(tool_name, []))
    
    # Add special tools if specified
    if "special_tools" in metadata:
        for special_tool in metadata["special_tools"]:
            if special_tool == "pdf_analyzer":
                agent_tools.extend(create_pdf_tools())
    
    # Add handoff tools to other active agents
    other_agents = [name for name in ACTIVE_AGENTS if name != agent_name]
    agent_handoffs = [handoff_tools.get(f"transfer_to_{other}") for other in other_agents]
    agent_handoffs = [tool for tool in agent_handoffs if tool is not None]
    
    # Create the agent
    agent = create_react_agent(
        model,
        prompt=metadata["prompt"],
        tools=agent_handoffs + agent_tools,
        name=agent_name,
    )
    
    return agent

# =============================================================================
# AGENT CREATION FUNCTIONS (LEGACY - TO BE REMOVED)
# =============================================================================

# LLM
model = init_chat_model(model="claude-3-5-haiku-20241022", model_provider="anthropic")

# Global MCP manager instance
mcp_manager = MCPManager()

# =============================================================================
# AGENT FACTORY SYSTEM
# =============================================================================

class AgentFactory:
    """Factory for creating agents conditionally based on configuration."""
    
    @staticmethod
    async def create_agent(agent_name: str, tools_dict: Dict, handoff_tools: Dict):
        """Create a specific agent by name using generic creation function."""
        return await create_generic_agent(agent_name, tools_dict, handoff_tools)
    
    @staticmethod
    async def create_active_agents(tools_dict: Dict, handoff_tools: Dict):
        """Create all active agents in parallel."""
        
        # Create tasks for parallel agent creation
        agent_tasks = {}
        for agent_name in ACTIVE_AGENTS:
            agent_tasks[agent_name] = asyncio.create_task(
                AgentFactory.create_agent(agent_name, tools_dict, handoff_tools)
            )
        
        # Wait for all agents to be created
        agents = {}
        failed_agents = []
        for agent_name, task in agent_tasks.items():
            try:
                agents[agent_name] = await task
            except Exception as e:
                failed_agents.append(f"{agent_name}: {e}")
        
        return agents, failed_agents

# =============================================================================
# MAIN APPLICATION CREATION
# =============================================================================

def print_mcp_status(tools):
    """Print MCP server connection status summary."""
    connected_servers = []
    failed_servers = []
    
    # Expected MCP servers
    expected_servers = ["sequential_thinking", "desktop_commander", "context7", "serena"]
    
    for server_name in expected_servers:
        if server_name in tools and tools[server_name]:
            connected_servers.append(server_name)
        else:
            failed_servers.append(server_name)
    
    # Print status
    if connected_servers:
        print(f"📊 MCP Servers: {', '.join(connected_servers)}")
    
    if failed_servers:
        for server in failed_servers:
            print(f"❌ {server}: connection failed")

def print_agent_status(agents, failed_agents):
    """Print agent creation status summary."""
    if agents:
        agent_names = list(agents.keys())
        default_agent = ACTIVE_AGENTS[0] if ACTIVE_AGENTS else "none"
        
        # Create different emojis for different agents
        agent_display = []
        for agent in agent_names:
            agent_display.append(f"{agent}")
        
        print(f"✅ Active Agents: {', '.join(agent_display)} (Default: {default_agent})")
    
    if failed_agents:
        for failure in failed_agents:
            print(f"❌ {failure}")

async def create_app():
    """Create the agent swarm app with configuration"""
    
    # Validate configuration
    validate_agent_config()
    
    try:
        # Initialize MCP servers
        tools = await mcp_manager.initialize_all_servers()
        
        # Print MCP status
        print_mcp_status(tools)
        
        # Create handoff tools for active agents
        handoff_tools = create_handoff_tools()
        
        # Create active agents using factory
        agents, failed_agents = await AgentFactory.create_active_agents(tools, handoff_tools)
        
        # Print agent status
        print_agent_status(agents, failed_agents)
        
        # Convert agents dict to list for swarm creation (order matters)
        agent_list = [agents[agent_name] for agent_name in ACTIVE_AGENTS if agent_name in agents]
        
        if not agent_list:
            raise ValueError("No agents were successfully created")
        
        # Create swarm with dynamic default agent
        default_agent = ACTIVE_AGENTS[0]  # First active agent becomes default
        
        checkpointer = InMemorySaver()
        agent_swarm = create_swarm(
            agent_list, 
            default_active_agent=default_agent,
            state_schema=AutoDRP_state
        )
        
        compiled_app = agent_swarm.compile(checkpointer=checkpointer)
        
        return compiled_app
        
    except Exception as e:
        print(f"❌ App creation failed: {e}")
        mcp_manager.stop_all_servers()
        raise

# Main application entry point
async def app():
    """Main application entry point - creates new instance each time"""
    try:
        return await create_app()
    except Exception as e:
        print(f"❌ Fatal error in app() entry point: {e}")
        await cleanup_resources()
        raise

async def cleanup_resources():
    """Clean up MCP servers and other resources"""
    try:
        mcp_manager.stop_all_servers()
    except Exception as cleanup_error:
        print(f"❌ Failed to clean up resources: {cleanup_error}")

# Graceful shutdown handler
import signal
import atexit

def setup_graceful_shutdown():
    """Setup graceful shutdown handlers"""
    def signal_handler(signum, frame):
        asyncio.create_task(cleanup_resources())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(lambda: asyncio.run(cleanup_resources()))

def load_environment_variable(env_var_name: str) -> str:
    """Load an environment variable with error handling."""
    value = os.environ.get(env_var_name)
    if not value:
        print(f"⚠️ Environment variable {env_var_name} not found")
    return value or ""

# =============================================================================
# UTILITIES
# =============================================================================

def print_config():
    """Print current configuration."""
    print(f"🔬 {', '.join(ACTIVE_AGENTS)} (Default: {ACTIVE_AGENTS[0]})")

def set_active_agents(agent_list: List[str]):
    """Dynamically change active agents (for programmatic control)."""
    global ACTIVE_AGENTS
    ACTIVE_AGENTS = agent_list
    validate_agent_config()
    print(f"🔄 Updated active agents: {', '.join(ACTIVE_AGENTS)}")

# Print configuration on import
if __name__ != "__main__":
    print_config()