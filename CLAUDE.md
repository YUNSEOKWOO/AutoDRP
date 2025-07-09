# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start the development server with LangGraph CLI
uvx --refresh --from "langgraph-cli[inmem]" --with-editable . --python 3.11 langgraph dev
```

### Code Quality
```bash
# Run linting with Ruff
ruff check src/
ruff check --fix src/  # Auto-fix issues

# Run type checking with mypy
mypy src/
```

### Installation Requirements
AutoDRP uses Docker containers for MCP servers via MCP Gateway mode:
```bash
# Start MCP server containers using provided script
./scripts/start-mcp.sh

# Stop MCP server containers
./scripts/stop-mcp.sh

# Verify containers are running
docker ps | grep mcp-
```

### Testing and Validation
```bash
# Test with LangGraph Studio (primary validation method)
uvx --refresh --from "langgraph-cli[inmem]" --with-editable . --python 3.11 langgraph dev
# Open LangGraph Studio UI to test agent interactions

# Install dependencies
pip install -e .
pip install -e ".[dev]"  # Install dev dependencies (mypy, ruff)
```

## Architecture Overview

### Multi-Agent LangGraph Swarm System
AutoDRP implements a **multi-agent coordination pattern** using LangGraph Swarm with 5 specialized agents that communicate through handoffs and shared state:

1. **analyzing_agent** (Default Active): Research paper analysis and code inspection
   - **Tools**: PDF analysis with RAG, Desktop Commander file ops, Sequential thinking
   - **Role**: Extract preprocessing requirements from papers and source code
   - **Handoffs**: To data_agent with preprocessing specs, to code_agent for execution details

2. **data_agent**: Custom data preprocessing pipeline creation
   - **Tools**: Desktop Commander for file operations, Sequential thinking, Serena MCP
   - **Role**: Create custom Python scripts for data transformation using Desktop Commander
   - **Pattern**: No pre-built data tools - dynamically creates analysis scripts per situation

3. **env_agent**: Docker environment and dependency management
   - **Tools**: Sequential thinking, Context7
   - **Role**: Build Docker images, manage containers, handle dependencies

4. **mcp_agent**: MCP server coordination and API wrapping
   - **Tools**: Sequential thinking, Context7
   - **Role**: Wrap models with FastAPI endpoints, convert to MCP servers

5. **code_agent**: Model execution and API communication
   - **Tools**: Sequential thinking, Desktop Commander
   - **Role**: Execute training/prediction tasks, communicate with containerized models

### Core Architectural Components

#### Agent Communication Architecture (`src/agent.py`)
- **Async Parallel Initialization**: All agents created concurrently using asyncio tasks
- **Transfer Tool Pattern**: Each agent has handoff tools to specific other agents
- **Default Active Agent**: System starts with analyzing_agent
- **Tool Composition Strategy**: 
  - Base: Sequential thinking for all agents
  - Specialized: PDF tools (analyzing_agent), Desktop Commander (analyzing + data agents)
- **Graceful Shutdown**: Signal handling and resource cleanup on termination

#### State Coordination System (`src/state.py`)
- **SwarmState Extension**: AutoDRP_state extends LangGraph Swarm's base state
- **Thread-Safe Global State**: GlobalStateManager with locking for concurrent access
- **Simple Dict-Based Storage**: No complex schemas, compatible with TypedDict requirements
- **State Operations**: PDF analysis storage, agent results, handoff context tracking
- **Legacy Compatibility**: Wrapper functions for existing state update patterns

#### MCP Gateway Architecture (`src/mcp.py`)
- **Docker Container Coordination**: MCPManager handles containerized MCP servers
- **Async Server Discovery**: Dynamic container detection and connection establishment
- **Multi-Transport Support**: stdio (sequential/desktop) and HTTP (context7) transports
- **Connection Resilience**: Retry logic, timeout handling, graceful degradation
- **Container Mapping**: Abstract server names to concrete container hosts/ports

#### PDF Analysis Pipeline (`src/utils.py`)
- **Intelligent Caching**: File modification time-based cache invalidation
- **Content Categorization**: Architecture, methodology, preprocessing keyword extraction  
- **RAG Integration**: Chroma vectorstore with OpenAI embeddings for semantic search
- **Performance Optimization**: Document chunking with overlap, lazy loading
- **State Integration**: Automatic PDF analysis result storage in global state

### Critical Design Patterns

#### Agent Specialization Pattern
Each agent has distinct responsibilities with minimal overlap:
- **analyzing_agent**: Research comprehension and requirement extraction
- **data_agent**: Dynamic preprocessing script generation (no built-in data tools)
- **Other agents**: Domain-specific tasks (env, mcp, code execution)

#### Custom Tool Creation Pattern (data_agent)
Instead of fixed data analysis tools, data_agent creates custom solutions:
```python
# Pattern: write_file() → execute_command() → iterate
write_file("analyze.py", custom_pandas_code)
execute_command("python analyze.py")
# Analyze results and create next script
```

#### MCP Server Abstraction
- **Gateway Mode**: Docker containers provide isolated MCP server environments
- **Tool Aggregation**: MCPManager collects tools from multiple servers into unified interface
- **Health Monitoring**: Container health checks ensure server availability

#### PDF Analysis Workflow
1. **Auto-discovery**: Find PDFs in models/ directory structure
2. **Cached Processing**: PyMuPDF loading with modification-time based caching
3. **Content Extraction**: Categorized keyword matching for technical content
4. **State Persistence**: Analysis results automatically saved for agent collaboration

### Configuration and Deployment

#### Container Orchestration (`docker-compose.mcp.yml`)
- **Isolated Network**: mcp-network bridge for container communication
- **Volume Mounting**: Host project directory mapped to /workspace in desktop-commander
- **Health Monitoring**: Process-based health checks with restart policies
- **Logging**: JSON file logging with rotation (10MB max, 3 files)

#### MCP Gateway Configuration (`mcp-gateway.json`)
- **Server Definitions**: Host/port mapping for each containerized MCP server
- **Transport Specification**: stdio vs HTTP transport per server type
- **Connection Tuning**: 10s timeout, 3 retries, configurable logging

#### LangGraph Integration (`langgraph.json`)
- **Entry Point**: `./src/agent.py:app` function as graph entry
- **Environment Loading**: `.env` file reference for configuration
- **Dependency Management**: Local package installation with editable mode

### Data Processing Philosophy

#### No-Assumptions Data Handling
The data_agent deliberately has no built-in data analysis capabilities, forcing custom solution creation for each unique dataset and requirement. This ensures flexibility but requires:
- **Creative Problem Solving**: Each situation gets custom Python script solutions
- **Desktop Commander Reliance**: All file operations through MCP tools
- **Iterative Development**: Create → test → refine cycle for data processing

#### Model-Driven Preprocessing
Preprocessing requirements come from analyzing_agent's paper/code analysis:
- **Paper Analysis**: Extract methodology and preprocessing steps from research papers
- **Code Inspection**: Analyze source code to understand exact data format requirements
- **Requirement Translation**: Convert research specifications to executable preprocessing steps

### Performance and Optimization

#### Caching Strategy
- **PDF Analysis**: File modification time-based cache keys prevent unnecessary reprocessing
- **Document Processing**: Chunk-level caching for large documents
- **State Updates**: Simple dict operations for minimal overhead

#### Async Patterns
- **Parallel Agent Creation**: All 5 agents initialized concurrently
- **Non-blocking MCP Initialization**: Server connections established asynchronously
- **Graceful Error Handling**: Individual server failures don't block entire system

### Key Implementation Notes

- **Default Active Agent**: analyzing_agent handles initial user requests
- **MCP Container Requirements**: Docker environment necessary for MCP server operation
- **State Compatibility**: All state operations maintain SwarmState/TypedDict compatibility
- **PDF Location**: System expects research papers in `models/` directory structure
- **Custom Script Pattern**: data_agent creates temporary Python scripts for all data operations
- **Environment Variable Support**: `.env` file loaded via langgraph.json reference
- **Package Management**: Uses pyproject.toml for dependency management with optional dev dependencies
- **Project Structure**: Source code in `src/` directory, packaged as `AutoDRP` module

### Development Constraints

- **No Manual Test Verification**: langgraph studio used for final validation by user
- **Rapid Prototyping Focus**: Initial logic construction over perfection
- **Pre-built Image Preference**: Use existing Docker images rather than building new ones
- **Build Constraints**: Docker image builds only possible in /home/ysu1516 directory
- **Script Coordination**: When changing container configurations, update corresponding scripts in `scripts/` directory
- **Container Management**: Use `scripts/start-mcp.sh` for starting MCP services, `scripts/stop-mcp.sh` for cleanup
- **MCP Container Network**: All MCP containers run on isolated `mcp-network` with automatic restart policies

### MCP Container Architecture

#### Active MCP Servers:
- **mcp-sequential**: Sequential thinking server (stdio transport)
- **mcp-desktop-commander**: File operations and command execution (stdio transport)
- **mcp-serena**: Advanced code analysis and writing (stdio transport)
- **mcp-context7**: Real-time documentation access (HTTP transport via port 8080)
- **mcp-gateway**: HTTP proxy for centralized access (nginx, port 8000)

#### Container Initialization Process:
1. **Network Setup**: Creates isolated `mcp-network` bridge
2. **Container Cleanup**: Stops and removes existing containers
3. **Service Startup**: Starts containers in dependency order
4. **Package Installation**: Installs data science packages in Serena container from `requirements_serena.txt`
5. **Health Checks**: Verifies all containers are running correctly