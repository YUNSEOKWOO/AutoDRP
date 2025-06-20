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

# Import MCP related functionality from separate module
# from AutoDRP.mcp import MCPManager, get_sequential_thinking_tools, get_desktop_commander_tools
from AutoDRP.mcp import MCPManager

# Import state schema and helper functions from local state module
from AutoDRP.state import AutoDRP_state, StateManager, AgentStatus, update_pdf_analysis, update_preprocessing_progress, update_raw_data_info, set_target_model

from AutoDRP.prompts import data_agent_prompt, env_agent_prompt, mcp_agent_prompt, code_agent_prompt, analyzing_prompt

from AutoDRP.utils import get_pdf_analyzer
import os

# LLM
model = init_chat_model(model="gpt-4o", model_provider="openai")

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

# Data agent - for data-related tasks
async def create_data_agent(sequential_thinking_tools, desktop_commander_tools):
    """Create data agent with Sequential Thinking and data processing tools."""
    from langchain_core.tools import tool
    import pandas as pd
    import os
    import glob
    from pathlib import Path
    
    @tool
    def scan_raw_data_directory() -> str:
        """Scan AutoDRP/data directory for available raw datasets."""
        try:
            data_paths = [
                "data",
                "./data",
                "../data"
            ]
            
            results = []
            for data_path in data_paths:
                if os.path.exists(data_path):
                    files = glob.glob(f"{data_path}/**/*", recursive=True)
                    data_files = [f for f in files if f.endswith(('.xlsx', '.csv', '.tsv', '.txt')) and os.path.isfile(f)]
                    
                    if data_files:
                        results.append(f"📁 {data_path}:")
                        for file_path in data_files[:10]:  # Limit to 10 files
                            file_size = os.path.getsize(file_path) // 1024  # KB
                            file_name = os.path.basename(file_path)
                            results.append(f"  📄 {file_name} ({file_size}KB)")
                        
                        if len(data_files) > 10:
                            results.append(f"  ... and {len(data_files) - 10} more files")
            
            return "\n".join(results) if results else "No data files found in expected directories"
            
        except Exception as e:
            return f"Error scanning data directory: {str(e)}"
    
    @tool
    def analyze_data_structure(file_path: str) -> str:
        """Analyze structure of a data file (xlsx, csv, tsv, txt)."""
        try:
            if not os.path.exists(file_path):
                return f"File not found: {file_path}"
            
            file_ext = Path(file_path).suffix.lower()
            results = [f"📄 File: {os.path.basename(file_path)}"]
            results.append(f"📊 Format: {file_ext}")
            results.append(f"💾 Size: {os.path.getsize(file_path) // 1024}KB")
            
            # Read file based on extension
            if file_ext == '.xlsx':
                df = pd.read_excel(file_path, nrows=5)
            elif file_ext == '.csv':
                df = pd.read_csv(file_path, nrows=5)
            elif file_ext == '.tsv':
                df = pd.read_csv(file_path, sep='\t', nrows=5)
            elif file_ext == '.txt':
                df = pd.read_csv(file_path, sep='\t', nrows=5)
            else:
                return f"Unsupported file format: {file_ext}"
            
            results.append(f"🏗️ Shape: {df.shape} (first 5 rows)")
            results.append(f"📋 Columns: {list(df.columns)}")
            results.append(f"🔍 Data types: {dict(df.dtypes)}")
            
            # Check for potential cell line columns
            cell_line_candidates = [col for col in df.columns if any(keyword in col.lower() for keyword in ['cell', 'line', 'sample', 'cosmic'])]
            if cell_line_candidates:
                results.append(f"🧬 Potential cell line columns: {cell_line_candidates}")
            
            return "\n".join(results)
            
        except Exception as e:
            return f"Error analyzing file structure: {str(e)}"
    
    @tool
    def map_cell_lines(drug_file: str, expression_file: str) -> str:
        """Map cell lines between drug-IC50 data and gene expression data."""
        try:
            # Load both files
            drug_df = pd.read_excel(drug_file) if drug_file.endswith('.xlsx') else pd.read_csv(drug_file)
            
            if expression_file.endswith('.xlsx'):
                expr_df = pd.read_excel(expression_file)
            elif expression_file.endswith('.txt') or expression_file.endswith('.tsv'):
                expr_df = pd.read_csv(expression_file, sep='\t')
            else:
                expr_df = pd.read_csv(expression_file)
            
            # Find cell line columns
            drug_cell_cols = [col for col in drug_df.columns if any(keyword in col.lower() for keyword in ['cell', 'line', 'sample', 'cosmic'])]
            expr_cell_cols = [col for col in expr_df.columns if any(keyword in col.lower() for keyword in ['cell', 'line', 'sample', 'cosmic'])]
            
            results = []
            results.append(f"📊 Drug data shape: {drug_df.shape}")
            results.append(f"📊 Expression data shape: {expr_df.shape}")
            results.append(f"🧬 Drug cell line columns: {drug_cell_cols}")
            results.append(f"🧬 Expression cell line columns: {expr_cell_cols}")
            
            if drug_cell_cols and expr_cell_cols:
                drug_cells = set(drug_df[drug_cell_cols[0]].unique())
                expr_cells = set(expr_df[expr_cell_cols[0]].unique())
                
                overlap = drug_cells.intersection(expr_cells)
                results.append(f"🔗 Cell line overlap: {len(overlap)} out of {len(drug_cells)} drug cells and {len(expr_cells)} expression cells")
                results.append(f"📋 Sample overlapping cells: {list(overlap)[:10]}")
            
            return "\n".join(results)
            
        except Exception as e:
            return f"Error mapping cell lines: {str(e)}"
    
    @tool
    def update_preprocessing_state(step: str, status: str, details: str = "") -> str:
        """Update preprocessing progress in swarm state."""
        try:
            # This would integrate with the actual state management
            # For now, return a status message
            return f"✅ Updated state: {step} - {status}. Details: {details}"
        except Exception as e:
            return f"Error updating state: {str(e)}"
    
    @tool
    def generate_preprocessing_script(model_requirements: str, data_info: str, output_filename: str) -> str:
        """Generate preprocessing script based on model requirements and data analysis."""
        try:
            # Handle path for Docker container - avoid data/ duplication
            clean_name = output_filename.lstrip('./')
            script_path = clean_name if clean_name.startswith('data/') else os.path.join("data", clean_name)
            
            # Basic preprocessing script template
            script_content = f'''#!/usr/bin/env python3
"""
Auto-generated preprocessing script for AutoDRP
Model requirements: {model_requirements}
Data info: {data_info}
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path

def preprocess_data():
    """Main preprocessing function."""
    print("Starting data preprocessing...")
    
    # Add specific preprocessing logic here based on model requirements
    # This is a template that should be customized
    
    print("Preprocessing completed successfully!")
    return True

if __name__ == "__main__":
    success = preprocess_data()
    if success:
        print("✅ Preprocessing script executed successfully")
    else:
        print("❌ Preprocessing failed")
'''
            
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            os.chmod(script_path, 0o755)  # Make executable
            
            return f"📄 Generated preprocessing script: {script_path}\\n\\nNext steps:\\n1. Customize the script with specific preprocessing logic\\n2. Execute the script using execute_preprocessing_script tool"
            
        except Exception as e:
            return f"Error generating preprocessing script: {str(e)}"
    
    @tool
    def execute_preprocessing_script(script_filename: str) -> str:
        """Execute preprocessing script in data directory."""
        try:
            # Handle path for Docker container - avoid data/ duplication
            clean_name = script_filename.lstrip('./')
            script_path = clean_name if clean_name.startswith('data/') else os.path.join("data", clean_name)
            
            if not os.path.exists(script_path):
                return f"❌ Script not found: {script_path}"
            
            import subprocess
            # Extract relative path from data directory for subprocess
            relative_path = script_path[5:] if script_path.startswith('data/') else script_path
            result = subprocess.run(
                ["python3", relative_path], 
                cwd="data",
                capture_output=True, 
                text=True
            )
            
            output = f"🔧 Executed: {script_filename}\\n"
            output += f"Return code: {result.returncode}\\n"
            
            if result.stdout:
                output += f"📤 Output:\\n{result.stdout}\\n"
            
            if result.stderr:
                output += f"⚠️ Errors:\\n{result.stderr}\\n"
            
            if result.returncode == 0:
                output += "✅ Script executed successfully!"
            else:
                output += "❌ Script execution failed!"
            
            return output
            
        except Exception as e:
            return f"Error executing preprocessing script: {str(e)}"
    
    @tool
    def validate_preprocessed_data(data_file: str, expected_format: str) -> str:
        """Validate preprocessed data against expected format."""
        try:
            # Handle path for Docker container - avoid data/ duplication
            clean_name = data_file.lstrip('./')
            data_path = clean_name if clean_name.startswith('data/') else os.path.join("data", clean_name)
            
            if not os.path.exists(data_path):
                return f"❌ Data file not found: {data_path}"
            
            # Load and analyze the data
            if data_file.endswith('.csv'):
                df = pd.read_csv(data_path)
            elif data_file.endswith('.xlsx'):
                df = pd.read_excel(data_path)
            elif data_file.endswith('.tsv') or data_file.endswith('.txt'):
                df = pd.read_csv(data_path, sep='\\t')
            else:
                return f"❌ Unsupported file format: {data_file}"
            
            validation_result = []
            validation_result.append(f"📊 File: {data_file}")
            validation_result.append(f"📏 Shape: {df.shape}")
            validation_result.append(f"📋 Columns: {list(df.columns)}")
            validation_result.append(f"🔍 Data types: {dict(df.dtypes)}")
            validation_result.append(f"📝 Expected format: {expected_format}")
            
            # Basic validation checks
            if df.empty:
                validation_result.append("❌ Warning: Data is empty")
            else:
                validation_result.append("✅ Data is not empty")
            
            if df.isnull().sum().sum() > 0:
                validation_result.append(f"⚠️ Missing values found: {df.isnull().sum().sum()} total")
            else:
                validation_result.append("✅ No missing values")
            
            return "\\n".join(validation_result)
            
        except Exception as e:
            return f"Error validating data: {str(e)}"
    
    data_agent = create_react_agent(
        model,
        prompt=data_agent_prompt,
        tools=[
            transfer_to_code_agent,
            transfer_to_analyzing_agent,
            scan_raw_data_directory,
            analyze_data_structure,
            map_cell_lines,
            update_preprocessing_state,
            generate_preprocessing_script,
            execute_preprocessing_script,
            validate_preprocessed_data
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


# Note: preload_all_mcp_tools is now imported from mcp module

async def create_app():
    """Create the agent swarm app with optimized initialization."""
    print("[INIT] Starting unified app initialization...")
    
    try:
        # 1. MCP 서버 직접 초기화 (더 이상 preload_all_mcp_tools()를 사용하지 않음)
        start_time = asyncio.get_event_loop().time()
        print("[INIT] Initializing MCP servers directly...")
        tools = await mcp_manager.initialize_all_servers()
        load_time = asyncio.get_event_loop().time() - start_time
        print(f"[INIT] MCP servers initialized in {load_time:.2f} seconds")
        
        # 2. 병렬로 모든 에이전트 생성
        print("[INIT] Creating all agents in parallel...")
        agent_start_time = asyncio.get_event_loop().time()
        
        # 모든 에이전트 생성 태스크 동시 실행
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
        
        # 모든 태스크 완료 대기
        data_agent = await data_agent_task
        env_agent = await env_agent_task
        mcp_agent = await mcp_agent_task
        code_agent = await code_agent_task
        analyzing_agent = await analyzing_agent_task
        
        agent_time = asyncio.get_event_loop().time() - agent_start_time
        print(f"[INIT] All agents created in {agent_time:.2f} seconds")
        
        # 3. 에이전트 스웜 생성 및 컴파일
        print("[INIT] Creating and compiling agent swarm...")
        swarm_start_time = asyncio.get_event_loop().time()
        
        # 인메모리 체크포인터 생성
        checkpointer = InMemorySaver()
        
        # 에이전트 스웜 생성
        agent_swarm = create_swarm(
            [data_agent, env_agent, mcp_agent, code_agent, analyzing_agent], 
            default_active_agent="analyzing_agent",
            state_schema=AutoDRP_state
        )
        
        # 스웜 컴파일
        compiled_app = agent_swarm.compile(checkpointer=checkpointer)
        
        swarm_time = asyncio.get_event_loop().time() - swarm_start_time
        total_time = asyncio.get_event_loop().time() - start_time
        
        print(f"[INIT] Agent swarm compiled in {swarm_time:.2f} seconds")
        print(f"[INIT] Total initialization completed in {total_time:.2f} seconds")
        
        return compiled_app
        
    except Exception as e:
        print(f"[ERROR] App initialization failed: {e}")
        # 오류 발생 시 모든 MCP 서버 종료
        mcp_manager.stop_all_servers()
        raise

# 글로벌 초기화 제어
_app_instance = None
_app_init_semaphore = asyncio.Semaphore(1)  # 세마포어로 동시 접근 제한
_app_init_started = False  # 초기화 시작 여부 추적
_app_init_count = 0  # 디버깅용 초기화 시도 카운트
_app_initialized_event = asyncio.Event()  # 초기화 완료 이벤트

async def get_app():
    """Get a singleton instance of the app with strict initialization control."""
    global _app_instance, _app_init_started, _app_init_count, _app_initialized_event
    
    # 이미 초기화된 앱이 있으면 즉시 반환
    if _app_instance is not None:
        return _app_instance
    
    # 초기화 요청 횟수 증가 (디버깅용)
    _app_init_count += 1
    request_id = _app_init_count
    
    # 이미 다른 요청에서 초기화 중인지 확인 (세마포어 획득 전)
    if _app_init_started:
        print(f"[APP:{request_id}] Initialization already in progress, waiting for event...")
        
        # 초기화 완료 이벤트 대기
        try:
            await asyncio.wait_for(_app_initialized_event.wait(), timeout=60.0)
            if _app_instance is not None:
                print(f"[APP:{request_id}] App initialized by another request, using existing instance")
                return _app_instance
        except asyncio.TimeoutError:
            print(f"[APP:{request_id}] Timeout waiting for initialization. Taking over...")
            # 타임아웃 시 초기화 재시작 (아래 코드로 진행)
    
    # 세마포어를 사용하여 단 하나의 요청만 초기화를 진행하도록 제한
    try:
        # 짧은 타임아웃으로 세마포어 획득 시도 (무한정 대기 방지)
        async with _app_init_semaphore:
            # 세마포어 획득 후 다시 확인 (경쟁 조건 방지)
            if _app_instance is not None:
                print(f"[APP:{request_id}] App already initialized after acquiring semaphore")
                return _app_instance
            
            try:
                # 초기화 시작 플래그 설정
                _app_init_started = True
                
                print(f"[APP:{request_id}] === APP INITIALIZATION STARTED (ONE TIME ONLY) ===")
                
                # 실제 앱 초기화
                start_time = asyncio.get_event_loop().time()
                _app_instance = await create_app()
                total_time = asyncio.get_event_loop().time() - start_time
                
                print(f"[APP:{request_id}] === APP INITIALIZATION COMPLETED in {total_time:.2f}s ===")
                
                # 초기화 완료 이벤트 설정
                _app_initialized_event.set()
                return _app_instance
                
            except Exception as e:
                print(f"[APP:{request_id}] !!! APP INITIALIZATION FAILED: {e}")
                # 초기화 실패 시 이벤트 설정 취소 (다른 요청이 시도할 수 있도록)
                _app_initialized_event.clear()
                raise
            finally:
                # 초기화 완료 또는 실패 시 플래그 해제
                _app_init_started = False
    except Exception as e:
        print(f"[APP:{request_id}] !!! Error during initialization control: {e}")
        raise

# Application entry point - ensures singleton initialization
async def app():
    """Application entry point that guarantees single initialization.
    This is the MAIN ENTRY POINT for the entire application!
    """
    global _app_initialized_event

    try:
        # 이벤트가 설정되지 않은 경우 (재시작 시나리오) 이벤트 초기화
        if _app_initialized_event is None:
            _app_initialized_event = asyncio.Event()
        
        # 모듈 초기화 시 항상 이벤트를 재설정하여 모듈 리로드 상황에서도 작동하도록 함
        if not _app_initialized_event.is_set() and _app_instance is not None:
            _app_initialized_event.set()
            
        print("[ENTRY] Entering application - guaranteed single initialization")
        return await get_app()
    except Exception as e:
        print(f"[ERROR] Fatal error in app() entry point: {e}")
        try:
            mcp_manager.stop_all_servers()  # 오류 발생 시 모든 서버 정리
        except Exception as cleanup_error:
            print(f"[ERROR] Failed to clean up MCP servers: {cleanup_error}")
        raise

# 2. Update the load_environment_variable function
def load_environment_variable(env_var_name: str) -> str:
    """Load an environment variable with error handling."""
    value = os.environ.get(env_var_name)
    if not value:
        print(f"[WARNING] Environment variable {env_var_name} not found")
    return value or ""
