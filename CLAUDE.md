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
Before running AutoDRP, install required MCP servers:
```bash
npm install -g @modelcontextprotocol/server-sequential-thinking
npm install -g @wonderwhy-er/desktop-commander
```

## Architecture Overview

### Multi-Agent System Structure
AutoDRP uses a **LangGraph Swarm** architecture with 5 specialized agents:

1. **analyzing_agent**: Main analysis agent with PDF processing and file system access
   - Tools: PDF analysis, Desktop Commander file operations, Sequential thinking
   - Role: Deep analysis of research papers and model implementations

2. **data_agent**: Handles data processing tasks
   - Tools: Desktop Commander file operations, Sequential thinking  
   - Role: Data preprocessing, file manipulation, dataset management

3. **env_agent**: Environment and configuration management
   - Tools: Sequential thinking
   - Role: Environment setup, dependency management

4. **mcp_agent**: MCP server coordination
   - Tools: Sequential thinking
   - Role: MCP server management and tool integration

5. **code_agent**: Code-related tasks
   - Tools: Sequential thinking
   - Role: Code generation, analysis, and implementation

### Core Components

#### State Management (`src/state.py`)
- **AutoDRP_state**: Simplified state schema extending SwarmState
- **StateManager**: Basic state operations for agent coordination
- Features: PDF analysis storage, agent results, handoff context

#### MCP Integration (`src/mcp.py`)
- **MCPManager**: Manages multiple MCP servers with async initialization
- Configuration-driven server management via `mcp.json`
- Concurrent server initialization with caching and error resilience

#### PDF Analysis (`src/utils.py`)
- **PDFAnalyzer**: Comprehensive PDF processing with caching
- RAG (Retrieval Augmented Generation) support with Chroma vectorstore
- Content categorization: architecture, methodology, preprocessing, hyperparameters
- Smart caching based on file modification times

#### Agent Factory (`src/agent.py`)
- Async agent creation with parallel initialization
- Tool composition: Sequential thinking + specialized tools per agent
- Error handling and performance optimization utilities

### Configuration Files

#### `mcp.json`
MCP server configuration with clean separation of concerns:
- Server definitions with enable/disable flags
- Transport and command specifications
- Startup requirements and timeout settings

#### `langgraph.json`
LangGraph CLI configuration:
- Graph entry point: `./src/agent.py:app`
- Environment file reference

#### `pyproject.toml`
Project dependencies and build configuration:
- Core: LangChain, LangGraph, LangGraph-Swarm
- MCP: langchain-mcp-adapters
- Document processing: PyMuPDF, Chroma
- Data: NumPy, Pandas

### Data Structure
- `models/`: Contains pre-trained models (DRPreter, NetGP) with datasets
- `data/`: Raw drug IC50 and gene expression data
- Source models include comprehensive datasets for drug-response prediction

### Key Design Patterns

#### Agent Handoffs
Agents use transfer tools to delegate tasks:
- `transfer_to_analyzing_agent`: For PDF and code analysis
- `transfer_to_data_agent`: For data processing
- Simple handoff context storage for coordination

#### Tool Composition
Each agent receives different tool combinations:
- All agents: Sequential thinking for step-by-step reasoning
- analyzing_agent + data_agent: Desktop Commander for file operations
- analyzing_agent: PDF tools for document analysis

#### Simplified State Management
- Dict-based state storage compatible with SwarmState/TypedDict
- Agent result storage for cross-agent communication
- Basic handoff context for task coordination
- No complex workflow tracking to reduce overhead

#### Performance Optimization
- Async/parallel agent initialization
- PDF analysis caching with modification time checks
- Simple dict-based state updates
- Minimal state validation for speed

## Important Notes

- The system expects PDF research papers in the `models/` directory structure
- MCP servers must be installed globally via npm before running
- State is preserved using simple dict-based storage compatible with SwarmState
- All file operations should use Desktop Commander tools rather than direct file I/O  
- PDF analysis results are automatically cached for performance
- Use simplified state tools: `save_agent_result`, `get_agent_result`, `set_handoff_info`, `get_handoff_info`, `view_current_state`