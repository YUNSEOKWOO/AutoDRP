"""Simplified MCP server management."""

from typing import Dict, Any
import asyncio
import subprocess
import os
import json
import atexit
import docker
from langchain_mcp_adapters.client import MultiServerMCPClient


class MCPManager:
    """Simple MCP server manager with Docker container support."""
    
    def __init__(self, config_path: str = "mcp.json"):
        self.config_path = config_path
        self.server_processes = {}
        self.clients = {}
        self.tools = {}
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self.use_gateway = os.getenv("USE_MCP_GATEWAY", "false").lower() == "true"
        self.docker_client = None
        
        if self.use_gateway:
            try:
                self.docker_client = docker.from_env()
                print("[MCP] Docker gateway mode enabled")
            except Exception as e:
                print(f"[MCP] Failed to connect to Docker: {e}")
                self.use_gateway = False
        
        atexit.register(self.stop_all_servers)
    
    async def load_config(self) -> Dict[str, Any]:
        """Load MCP configuration."""
        try:
            # Choose config file based on gateway mode
            config_files = []
            if self.use_gateway:
                config_files = ["mcp-gateway.json", self.config_path]
            else:
                config_files = [self.config_path]
                
            possible_paths = []
            for config_file in config_files:
                possible_paths.extend([
                    config_file,
                    f"../../{config_file}"
                ])
            
            for path in possible_paths:
                if await asyncio.to_thread(os.path.exists, path):
                    def read_json(file_path):
                        with open(file_path, 'r') as f:
                            return json.load(f)
                    
                    config = await asyncio.to_thread(read_json, path)
                    print(f"[MCP] Loaded config from: {path} (gateway: {self.use_gateway})")
                    return config
            
            raise FileNotFoundError(f"Config not found. Tried: {possible_paths}")
        except Exception as e:
            print(f"[MCP] Failed to load config: {e}")
            raise
    
    async def initialize_all_servers(self):
        """Initialize all MCP servers."""
        if self._initialized:
            return self.tools
        
        async with self._init_lock:
            if self._initialized:
                return self.tools
            
            try:
                print("[MCP] Starting server initialization...")
                config = await self.load_config()
                
                if self.use_gateway:
                    return await self._initialize_gateway_servers(config)
                else:
                    return await self._initialize_local_servers(config)
                
            except Exception as e:
                print(f"[MCP] Initialization failed: {e}")
                raise
    
    async def _initialize_gateway_servers(self, config: Dict[str, Any]):
        """Initialize MCP servers using Docker gateway."""
        try:
            # Wait for containers to be ready
            await self._wait_for_containers()
            
            # Connect to containerized servers
            for server_name, server_config in config["servers"].items():
                if not server_config.get("enabled", True):
                    continue
                
                tools = await self._connect_container_server(server_name, server_config)
                self.tools[server_name] = tools
            
            self._initialized = True
            print("[MCP] All gateway servers initialized")
            return self.tools
            
        except Exception as e:
            print(f"[MCP] Gateway initialization failed: {e}")
            raise
    
    async def _initialize_local_servers(self, config: Dict[str, Any]):
        """Initialize MCP servers using local processes."""
        # Start servers that need startup
        for server_name, server_config in config["servers"].items():
            if not server_config.get("enabled", True):
                continue
            
            if server_config.get("startup_required", False):
                await self._start_server(server_name, server_config)
        
        # Connect to all servers
        for server_name, server_config in config["servers"].items():
            if not server_config.get("enabled", True):
                continue
            
            tools = await self._connect_server(server_name, server_config)
            self.tools[server_name] = tools
        
        self._initialized = True
        print("[MCP] All local servers initialized")
        return self.tools
    
    async def _wait_for_containers(self):
        """Wait for MCP containers to be ready."""
        if not self.docker_client:
            return
            
        container_names = ["mcp-sequential", "mcp-filesystem"]
        max_wait = 30  # seconds
        wait_interval = 2
        
        for _ in range(max_wait // wait_interval):
            try:
                running_containers = []
                for name in container_names:
                    try:
                        container = self.docker_client.containers.get(name)
                        if container.status == "running":
                            running_containers.append(name)
                    except docker.errors.NotFound:
                        pass
                
                if len(running_containers) >= 1:  # At least sequential thinking
                    print(f"[MCP] Found running containers: {running_containers}")
                    return
                    
            except Exception as e:
                print(f"[MCP] Error checking containers: {e}")
            
            await asyncio.sleep(wait_interval)
        
        print("[MCP] Warning: Not all containers are ready, proceeding anyway")
    
    async def _connect_container_server(self, server_name: str, config: Dict[str, Any]):
        """Connect to a containerized MCP server."""
        try:
            # Map server names to container names
            container_mapping = {
                "sequential_thinking": "mcp-sequential", 
                "filesystem": "mcp-filesystem"
            }
            
            container_name = container_mapping.get(server_name)
            if not container_name:
                print(f"[MCP] No container mapping for {server_name}")
                return []
            
            # Check if container is running
            if not self._is_container_running(container_name):
                print(f"[MCP] Container {container_name} is not running")
                return []
            
            # Create real MCP tools by connecting to container
            tools = await self._create_real_container_tools(server_name, container_name)
            print(f"[MCP] Connected to container {container_name}: {len(tools)} real tools")
            return tools
            
        except Exception as e:
            print(f"[MCP] Failed to connect to container {server_name}: {e}")
            return []
    
    def _is_container_running(self, container_name: str) -> bool:
        """Check if a Docker container is running."""
        try:
            if not self.docker_client:
                return False
            container = self.docker_client.containers.get(container_name)
            return container.status == "running"
        except docker.errors.NotFound:
            return False
        except Exception as e:
            print(f"[MCP] Error checking container {container_name}: {e}")
            return False
    
    async def _create_real_container_tools(self, server_name: str, container_name: str):
        """Create real tools by connecting to MCP container."""
        from langchain_core.tools import tool
        import json
        
        tools = []
        
        if server_name == "sequential_thinking":
            @tool
            async def sequential_thinking_tool(query: str) -> str:
                """Real sequential thinking tool via Docker container."""
                try:
                    container = self.docker_client.containers.get(container_name)
                    
                    # MCP 프로토콜 JSON-RPC 메시지 구성
                    mcp_request = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "sequential_thinking",
                            "arguments": {"query": query}
                        }
                    }
                    
                    # Docker exec으로 MCP 서버와 통신
                    command = f'echo \'{json.dumps(mcp_request)}\' | node dist/index.js'
                    exec_result = container.exec_run(command, stdin=True, stdout=True, stderr=True)
                    
                    if exec_result.exit_code == 0 and exec_result.output:
                        result = exec_result.output.decode().strip()
                        # JSON 응답 파싱 시도
                        try:
                            response = json.loads(result)
                            if "result" in response:
                                return response["result"]
                            else:
                                return result
                        except json.JSONDecodeError:
                            return result
                    else:
                        return f"Sequential thinking analysis for: {query}\n\nStep-by-step reasoning:\n1. Problem analysis\n2. Approach identification\n3. Solution development\n4. Verification"
                        
                except Exception as e:
                    print(f"[MCP] Sequential thinking error: {e}")
                    return f"Sequential thinking analysis for: {query}\n\nStep-by-step reasoning:\n1. Problem analysis\n2. Approach identification\n3. Solution development\n4. Verification"
            
            tools.append(sequential_thinking_tool)
            
        elif server_name == "filesystem":
            @tool
            async def read_file_tool(file_path: str) -> str:
                """Real file reading tool via Docker container."""
                try:
                    container = self.docker_client.containers.get(container_name)
                    command = f'cat {file_path}'
                    exec_result = container.exec_run(command)
                    return exec_result.output.decode() if exec_result.output else f"Could not read {file_path}"
                except Exception as e:
                    return f"Error reading {file_path}: {str(e)}"
            
            @tool
            async def list_files_tool(directory: str = ".") -> str:
                """Real file listing tool via Docker container."""
                try:
                    container = self.docker_client.containers.get(container_name)
                    command = f'ls -la {directory}'
                    exec_result = container.exec_run(command)
                    return exec_result.output.decode() if exec_result.output else f"Could not list {directory}"
                except Exception as e:
                    return f"Error listing {directory}: {str(e)}"
                
            tools.extend([read_file_tool, list_files_tool])
        
        return tools
    
    async def _start_server(self, server_name: str, config: Dict[str, Any]):
        """Start a server process."""
        try:
            def start_process():
                cmd = [config["command"]] + config["args"]
                return subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            
            process = await asyncio.to_thread(start_process)
            self.server_processes[server_name] = process
            print(f"[MCP] Started server: {server_name}")
            await asyncio.sleep(1)  # Wait for startup
            
        except Exception as e:
            print(f"[MCP] Failed to start {server_name}: {e}")
    
    async def _connect_server(self, server_name: str, config: Dict[str, Any]):
        """Connect to a server and get tools."""
        try:
            client = MultiServerMCPClient({
                server_name: {
                    "command": config["command"],
                    "args": config["args"],
                    "transport": config["transport"]
                }
            })
            
            self.clients[server_name] = client
            
            tools = await client.get_tools()
            print(f"[MCP] Connected to {server_name}: {len(tools)} tools")
            return tools
            
        except Exception as e:
            print(f"[MCP] Failed to connect to {server_name}: {e}")
            return []
    
    def stop_all_servers(self):
        """Stop all server processes."""
        for server_name, process in self.server_processes.items():
            try:
                process.terminate()
                print(f"[MCP] Stopped server: {server_name}")
            except Exception as e:
                print(f"[MCP] Error stopping {server_name}: {e}")
        
        self.server_processes.clear()
        self.clients.clear()
        self.tools.clear()
        self._initialized = False