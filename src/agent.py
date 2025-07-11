from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.tools import tool
from typing import Dict, List
import asyncio
import os
import signal
import atexit

from AutoDRP.mcp_manager import MCPManager
from AutoDRP.state import AutoDRP_state
from AutoDRP.prompts import data_agent_prompt, env_agent_prompt, mcp_agent_prompt, code_agent_prompt, analyzing_prompt
from AutoDRP.utils import get_pdf_analyzer


# =============================================================================
#  USER CONFIGURATION - 사용자가 직접 설정하는 항목들
# =============================================================================

# LLM 모델 설정
MODEL_NAME = "claude-3-5-haiku-20241022"
MODEL_PROVIDER = "anthropic"

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
        "prompt": "analyzing_prompt",
        "mcp_tools": ["mcp-sequential", "mcp-desktop-commander", "mcp-serena"],
        "special_tools": ["pdf_analyzer"],
        "description": "Research paper analysis and code inspection"
    },
    "data_agent": {
        "prompt": "data_agent_prompt",
        "mcp_tools": ["mcp-sequential", "mcp-desktop-commander", "mcp-context7", "mcp-serena"],
        "description": "Custom data preprocessing pipeline creation"
    },
    "env_agent": {
        "prompt": "env_agent_prompt", 
        "mcp_tools": ["mcp-sequential", "mcp-context7"],
        "description": "Docker environment and dependency management"
    },
    "mcp_agent": {
        "prompt": "mcp_agent_prompt",
        "mcp_tools": ["mcp-sequential", "mcp-context7"],
        "description": "MCP server coordination and API wrapping"
    },
    "code_agent": {
        "prompt": "code_agent_prompt",
        "mcp_tools": ["mcp-sequential", "mcp-desktop-commander"],
        "description": "Model execution and API communication"
    }
}


# =============================================================================
#  CORE LOGIC
# =============================================================================

# Initialize LLM and MCP manager
model = init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER)
mcp_manager = MCPManager()

def validate_config():
    """Validate configuration."""
    if not ACTIVE_AGENTS:
        raise ValueError("At least one agent must be active")
    
    invalid_agents = [agent for agent in ACTIVE_AGENTS if agent not in AGENT_METADATA]
    if invalid_agents:
        raise ValueError(f"Invalid agent names: {invalid_agents}")

def create_handoff_tools():
    """Create handoff tools for active agents."""
    handoff_tools = {}
    
    for agent_name in ACTIVE_AGENTS:
        tool_name = f"transfer_to_{agent_name}"
        description = f"Transfer to {agent_name} for {AGENT_METADATA[agent_name]['description']}."
        
        handoff_tools[tool_name] = create_handoff_tool(
            agent_name=agent_name,
            description=description
        )
        
    return handoff_tools

def create_pdf_tools():
    """Create PDF analysis tools."""
    pdf_analyzer = get_pdf_analyzer()
    
    @tool
    def analyze_pdfs(query: str = "") -> str:
        """Analyze PDF documents in models directory."""
        try:
            pdf_files = pdf_analyzer.find_pdf_files()
            if not pdf_files:
                return "No PDF files found in models directory"
            
            results = []
            for pdf_path in pdf_files[:3]:
                analysis = pdf_analyzer.analyze_content(pdf_path, query)
                if "error" not in analysis:
                    pdf_name = os.path.basename(pdf_path)
                    total_chunks = analysis.get('total_chunks', 0)
                    results.append(f"📄 {pdf_name}: {total_chunks} chunks analyzed")
                else:
                    results.append(f"❌ {os.path.basename(pdf_path)}: {analysis['error']}")
            
            return "\\n".join(results)
        except Exception as e:
            return f"Error analyzing PDFs: {str(e)}"
    
    @tool
    def find_pdf_files() -> str:
        """Find all available PDF files."""
        try:
            pdf_files = pdf_analyzer.find_pdf_files()
            if not pdf_files:
                return "No PDF files found"
            
            file_list = [f"📄 {os.path.basename(pdf)}" for pdf in pdf_files]
            return f"Found {len(pdf_files)} PDFs:\\n" + "\\n".join(file_list)
        except Exception as e:
            return f"Error finding PDFs: {str(e)}"
    
    return [analyze_pdfs, find_pdf_files]

async def create_agent(agent_name: str, tools_dict: Dict, handoff_tools: Dict):
    """Create a single agent."""
    if agent_name not in AGENT_METADATA:
        raise ValueError(f"Unknown agent: {agent_name}")
    
    metadata = AGENT_METADATA[agent_name]
    
    # Get prompt function by name
    prompt_name = metadata["prompt"]
    prompt_func = globals().get(prompt_name)
    if not prompt_func:
        raise ValueError(f"Prompt function {prompt_name} not found")
    
    # Build tools list
    agent_tools = []
    for tool_name in metadata["mcp_tools"]:
        agent_tools.extend(tools_dict.get(tool_name, []))
    
    # Add special tools
    if "special_tools" in metadata and "pdf_analyzer" in metadata["special_tools"]:
        agent_tools.extend(create_pdf_tools())
    
    # Add handoff tools to other agents
    other_agents = [name for name in ACTIVE_AGENTS if name != agent_name]
    agent_handoffs = [handoff_tools.get(f"transfer_to_{other}") for other in other_agents]
    agent_handoffs = [tool for tool in agent_handoffs if tool is not None]
    
    return create_react_agent(
        model,
        prompt=prompt_func,
        tools=agent_handoffs + agent_tools,
        name=agent_name,
    )

async def create_all_agents(tools_dict: Dict, handoff_tools: Dict):
    """Create all active agents in parallel."""
    agent_tasks = {
        agent_name: asyncio.create_task(create_agent(agent_name, tools_dict, handoff_tools))
        for agent_name in ACTIVE_AGENTS
    }
    
    agents = {}
    failed_agents = []
    
    for agent_name, task in agent_tasks.items():
        try:
            agents[agent_name] = await task
        except Exception as e:
            failed_agents.append(f"{agent_name}: {e}")
    
    return agents, failed_agents

# =============================================================================
#  APPLICATION CREATION
# =============================================================================

def print_status(tools, agents, failed_agents):
    """Print system status."""
    # MCP status - load from MCP_NAMES environment variable
    mcp_names = os.getenv('MCP_NAMES', '').strip()
    expected_servers = mcp_names.split() if mcp_names else []
    
    connected = [s for s in expected_servers if s in tools and tools[s]]
    failed = [s for s in expected_servers if s not in connected]
    
    if connected:
        print(f"📊 MCP Servers: {', '.join(connected)}")
    if failed:
        print(f"❌ Failed MCP: {', '.join(failed)}")
    
    # Agent status
    if agents:
        default = ACTIVE_AGENTS[0] if ACTIVE_AGENTS else "none"
        print(f"✅ Agents: {', '.join(agents.keys())} (Default: {default})")
    if failed_agents:
        for failure in failed_agents:
            print(f"❌ {failure}")

async def create_app():
    """Create the main application."""
    validate_config()
    
    try:
        # Initialize MCP servers
        tools = await mcp_manager.initialize_all_servers()
        
        # Create handoff tools and agents
        handoff_tools = create_handoff_tools()
        agents, failed_agents = await create_all_agents(tools, handoff_tools)
        
        # Print status
        print_status(tools, agents, failed_agents)
        
        # Create agent list in order
        agent_list = [agents[name] for name in ACTIVE_AGENTS if name in agents]
        
        if not agent_list:
            raise ValueError("No agents were successfully created")
        
        # Create swarm
        checkpointer = InMemorySaver()
        agent_swarm = create_swarm(
            agent_list, 
            default_active_agent=ACTIVE_AGENTS[0],
            state_schema=AutoDRP_state
        )
        
        return agent_swarm.compile(checkpointer=checkpointer)
        
    except Exception as e:
        print(f"❌ App creation failed: {e}")
        mcp_manager.stop_all_servers()
        raise

# =============================================================================
#  MAIN ENTRY POINTS
# =============================================================================

async def app():
    """Main application entry point."""
    try:
        return await create_app()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        await cleanup_resources()
        raise

async def cleanup_resources():
    """Clean up resources."""
    try:
        mcp_manager.stop_all_servers()
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")

# =============================================================================
#  UTILITIES
# =============================================================================

def setup_graceful_shutdown():
    """Setup graceful shutdown handlers."""
    def signal_handler(signum, frame):
        asyncio.create_task(cleanup_resources())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(lambda: asyncio.run(cleanup_resources()))

def print_config():
    """Print current configuration."""
    if ACTIVE_AGENTS:
        print(f"🔬 Active: {', '.join(ACTIVE_AGENTS)} (Default: {ACTIVE_AGENTS[0]})")
    else:
        print("⚠️ No active agents configured")

def set_active_agents(agent_list: List[str]):
    """Dynamically change active agents."""
    global ACTIVE_AGENTS
    ACTIVE_AGENTS = agent_list
    validate_config()
    print(f"🔄 Updated agents: {', '.join(ACTIVE_AGENTS)}")

# Print configuration on import
if __name__ != "__main__":
    print_config()