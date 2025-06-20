# AutoDRP Example

A two-phase multi-agent system that demonstrates an effective collaborative approach to planning and research tasks. This example showcases a pattern used in many deep research systems:

1. **Planning Phase**: A dedicated planner agent clarifies requirements, reads documentation, and develops a structured approach
2. **Research Phase**: A researcher agent implements the solution based on the planner's guidance

## Quickstart

```bash
uvx --refresh --from "langgraph-cli[inmem]" --with-editable . --python 3.11 langgraph dev
```

## How It Works

- The system starts with the **planner agent** that:
  - Analyzes the user's request
  - Reads relevant documentation
  - Asks clarifying questions to refine scope
  - Creates a structured plan with clear objectives
  - Identifies the most relevant resources for implementation
  - Hands off to the researcher agent

- The **researcher agent** then:
  - Follows the structured plan from the planner
  - Reads the recommended documentation sources
  - Implements the solution to satisfy all requirements
  - Can request additional planning if needed

This pattern demonstrates how breaking complex tasks into planning and execution phases can lead to more thorough, well-researched outcomes.

# AutoDRP with Enhanced File System Access

This AutoDRP system includes multiple specialized agents for comprehensive analysis of drug-response prediction models, with enhanced file system access capabilities.

## Agents

- **analyzing_agent**: Main analysis agent with PDF processing and **file system access** capabilities
- **data_agent**: Handles data-related tasks
- **env_agent**: Manages environment-related tasks  
- **mcp_agent**: Handles MCP-related tasks
- **code_agent**: Manages code-related tasks

## New Feature: File System Access via DesktopCommanderMCP

The analyzing_agent now includes **DesktopCommanderMCP** integration, providing direct access to:

### File System Capabilities
- **Directory listing**: Navigate and explore folder structures
- **File reading**: Read source code, configuration files, and documentation
- **File searching**: Search for patterns and content within files
- **File metadata**: Get detailed information about files
- **Pattern matching**: Find files by name or pattern across directory trees
- **Terminal access**: Execute commands for additional analysis

### Enhanced Analysis Workflow

The analyzing_agent can now:

1. **Explore Models Directory**: Directly access `models/NetGP/`, `models/DRPreter/`, and other model directories
2. **Read Source Code**: Analyze Python files, Jupyter notebooks, configuration files
3. **Compare Implementations**: Cross-reference code with research papers
4. **Extract Dependencies**: Read requirements.txt and import statements
5. **Analyze File Structure**: Understand project organization and architecture

## Installation Requirements

Before running AutoDRP, install the required MCP servers:

```bash
# Install required MCP servers globally
npm install -g @modelcontextprotocol/server-sequential-thinking
npm install -g @wonderwhy-er/desktop-commander
npm install -g @modelcontextprotocol/server-filesystem
```

## Configuration

The system uses a JSON-based configuration file (`mcp.json`) for clean separation of MCP server settings:

```json
{
  "servers": {
    "sequential_thinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
      "transport": "stdio",
      "description": "Sequential thinking MCP server for step-by-step reasoning",
      "enabled": true,
      "startup_required": true
    },
    "desktop_commander": {
      "command": "npx", 
      "args": ["-y", "@wonderwhy-er/desktop-commander"],
      "transport": "stdio",
      "description": "Desktop Commander MCP server for file system operations",
      "enabled": true,
      "startup_required": false
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app/workspace/langgraph-swarm-py/examples/research"],
      "transport": "stdio",
      "description": "Filesystem MCP server for enhanced file operations",
      "enabled": true,
      "startup_required": false
    }
  },
  "settings": {
    "startup_timeout": 5,
    "connection_retry_count": 3,
    "cache_tools": true,
    "concurrent_initialization": true
  }
}
```

### Adding New MCP Servers

To add a new MCP server, simply update the `mcp.json` file:

1. Add a new server entry under `"servers"`
2. Set `"enabled": true` to activate it
3. Configure `"startup_required"` if the server needs explicit startup
4. The system will automatically load and integrate the new server

## Usage Example

The analyzing_agent can now perform comprehensive analysis like:

```python
# The agent can now:
# 1. List all files in models directory
# 2. Read model source code files
# 3. Extract hyperparameters from configuration files
# 4. Analyze import dependencies
# 5. Cross-reference with PDF papers
# 6. Generate FastAPI integration recommendations
```

## Tools Available to Analyzing Agent

### PDF Analysis Tools
- `create_rag_retriever`: Create searchable index from PDF papers
- `load_pdf_document`: Load and chunk PDF content  
- `analyze_pdf_content`: Extract and categorize PDF information

### File System Access Tools (NEW)
- **Desktop Commander Tools**: File system operations, directory listing, file reading
- **Filesystem Tools**: Enhanced file operations with workspace-specific access
- Terminal execution capabilities for advanced analysis

### Thinking Tools
- `sequentialthinking`: Systematic step-by-step analysis

## Architecture Benefits

### JSON-Based Configuration
- **Clean Separation**: Settings separated from code logic
- **Easy Maintenance**: Add/remove MCP servers by editing JSON
- **Environment Flexibility**: Different configs for different environments
- **Fallback Support**: Automatic fallback to default configuration

### Unified MCP Management
- **Single Manager**: One `MCPManager` class handles all servers
- **Efficient Caching**: Tools cached to avoid repeated initialization
- **Concurrent Safe**: Proper locking for multi-threaded environments
- **Error Resilient**: Individual server failures don't affect others

This combination enables comprehensive analysis of both research papers (PDFs) and implementation code (source files) for complete model understanding and FastAPI integration planning.

