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


# LLM
model = init_chat_model(model="claude-3-5-haiku-20241022", model_provider="anthropic")

# Handoff tools
transfer_to_data_agent = create_handoff_tool(
    agent_name="data_agent",
    description="Transfer the user to the data_agent for data-processing tasks.",
)
transfer_to_env_agent = create_handoff_tool(
    agent_name="env_agent",
    description="Transfer the user to the env_agent for environment-related tasks.",
)
transfer_to_mcp_agent = create_handoff_tool(
    agent_name="mcp_agent",
    description="Transfer the user to the mcp_agent for MCP-related tasks.",
)
transfer_to_code_agent = create_handoff_tool(
    agent_name="code_agent",
    description="Transfer the user to the code_agent for code-related tasks.",
)
transfer_to_analyzing_agent = create_handoff_tool(
    agent_name="analyzing_agent", 
    description="Transfer the user to the analyzing_agent to perform deep analysis of research papers (PDF files) and extract technical implementation details.",
)

# Global MCP manager instance
mcp_manager = MCPManager()


# Utility functions for token optimization
def limit_output(text: str, max_length: int = 1000) -> str:
    """출력 텍스트 길이 제한으로 토큰 사용량 최적화"""
    if len(text) <= max_length:
        return text
    return text[:max_length-10] + "...[생략]"

def compress_debug_output(text: str, max_length: int = 200) -> str:
    """디버그/로그 출력만 압축 (AutoDRP_state 정보는 제외)"""
    # AutoDRP_state 관련 정보는 압축하지 않음
    if any(keyword in text.lower() for keyword in ['autodrp_state', 'pdf_analysis', 'preprocessing_progress', 'raw_data_info']):
        return text
    
    # 일반 디버그 출력만 압축
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

# Data agent - for data-related tasks
async def create_data_agent(sequential_thinking_tools, desktop_commander_tools):
    """Create data agent with Sequential Thinking and Desktop Commander tools only."""
    
    data_agent = create_react_agent(
        model,
        prompt=data_agent_prompt,
        tools=[
            transfer_to_code_agent,
            transfer_to_analyzing_agent,
            # No custom tools - Agent uses Desktop Commander for all data operations
        ] + sequential_thinking_tools + desktop_commander_tools,
        name="data_agent",
    )
    return data_agent

# Environment agent - for environment-related tasks
async def create_env_agent(sequential_thinking_tools):
    """Create environment agent with Sequential Thinking tools."""
    env_agent = create_react_agent(
        model,
        prompt=env_agent_prompt,
        tools=[
            transfer_to_code_agent,
            transfer_to_analyzing_agent
        ] + sequential_thinking_tools,
        name="env_agent",
    )
    return env_agent

# MCP agent - for MCP-related tasks
async def create_mcp_agent(sequential_thinking_tools):
    """Create MCP agent with Sequential Thinking tools."""
    mcp_agent = create_react_agent(
        model,
        prompt=mcp_agent_prompt,
        tools=[
            transfer_to_code_agent,
            transfer_to_analyzing_agent
        ] + sequential_thinking_tools,
        name="mcp_agent",
    )
    return mcp_agent

# Code agent
async def create_code_agent(sequential_thinking_tools):
    """Create code agent with Sequential Thinking tools."""
    code_agent = create_react_agent(
        model,
        prompt=code_agent_prompt,
        tools=[
            transfer_to_data_agent,
            transfer_to_env_agent,
            transfer_to_mcp_agent,
            transfer_to_analyzing_agent
        ] + sequential_thinking_tools,
        name="code_agent",
    )
    return code_agent


async def create_analyzing_agent(sequential_thinking_tools, desktop_commander_tools):
    """Create analyzing agent with PDF and code analysis tools."""
    print("[INIT] Creating analyzing agent...")
    
    try:
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
        
        # Create analyzing agent with PDF analysis tools
        analyzing_agent = create_react_agent(
            model,
            prompt=analyzing_prompt,
            tools=[
                transfer_to_data_agent,
                transfer_to_env_agent,
                transfer_to_mcp_agent,
                transfer_to_code_agent,
                analyze_pdfs,
                find_pdf_files,
                get_pdf_summary
            ] + sequential_thinking_tools + desktop_commander_tools,
            name="analyzing_agent",
        )
        
        print("[INIT] Analyzing agent created successfully")
        return analyzing_agent
        
    except Exception as e:
        print(f"[ERROR] Failed to create analyzing agent: {e}")
        raise


async def create_app():
    """Create the agent swarm app with parallel initialization"""
    print("[INIT] Creating app...")
    
    try:
        # MCP 서버 초기화
        start_time = asyncio.get_event_loop().time()
        tools = await mcp_manager.initialize_all_servers()
        load_time = asyncio.get_event_loop().time() - start_time
        print(f"[INIT] MCP servers initialized in {load_time:.2f} seconds")
        
        # 병렬 에이전트 생성
        data_agent_task = asyncio.create_task(create_data_agent(tools["sequential_thinking"], tools["desktop_commander"]))
        env_agent_task = asyncio.create_task(create_env_agent(tools["sequential_thinking"]))
        mcp_agent_task = asyncio.create_task(create_mcp_agent(tools["sequential_thinking"]))
        code_agent_task = asyncio.create_task(create_code_agent(tools["sequential_thinking"]))
        analyzing_agent_task = asyncio.create_task(
            create_analyzing_agent(
                tools["sequential_thinking"], 
                tools["desktop_commander"]
            )
        )
        
        # 모든 에이전트 생성 완료 대기
        data_agent = await data_agent_task
        env_agent = await env_agent_task
        mcp_agent = await mcp_agent_task
        code_agent = await code_agent_task
        analyzing_agent = await analyzing_agent_task
        
        # 스웜 생성 및 컴파일
        checkpointer = InMemorySaver()
        agent_swarm = create_swarm(
            [data_agent, env_agent, mcp_agent, code_agent, analyzing_agent], 
            default_active_agent="analyzing_agent",
            state_schema=AutoDRP_state
        )
        
        compiled_app = agent_swarm.compile(checkpointer=checkpointer)
        total_time = asyncio.get_event_loop().time() - start_time
        print(f"[INIT] App created successfully in {total_time:.2f} seconds")
        
        return compiled_app
        
    except Exception as e:
        print(f"[INIT] App creation failed: {e}")
        mcp_manager.stop_all_servers()
        raise

# Main application entry point
async def app():
    """Main application entry point - creates new instance each time"""
    try:
        print("[ENTRY] Creating new app instance...")
        return await create_app()
    except Exception as e:
        print(f"[ERROR] Fatal error in app() entry point: {e}")
        await cleanup_resources()
        raise

async def cleanup_resources():
    """Clean up MCP servers and other resources"""
    try:
        print("[CLEANUP] Stopping MCP servers...")
        mcp_manager.stop_all_servers()
        print("[CLEANUP] Resource cleanup completed")
    except Exception as cleanup_error:
        print(f"[ERROR] Failed to clean up resources: {cleanup_error}")

# Graceful shutdown handler
import signal
import atexit

def setup_graceful_shutdown():
    """Setup graceful shutdown handlers"""
    def signal_handler(signum, frame):
        print(f"[SHUTDOWN] Received signal {signum}, cleaning up...")
        asyncio.create_task(cleanup_resources())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(lambda: asyncio.run(cleanup_resources()))

# 2. Update the load_environment_variable function
def load_environment_variable(env_var_name: str) -> str:
    """Load an environment variable with error handling."""
    value = os.environ.get(env_var_name)
    if not value:
        print(f"[WARNING] Environment variable {env_var_name} not found")
    return value or ""
