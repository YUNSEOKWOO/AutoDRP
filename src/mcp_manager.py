"""Simplified MCP server management."""

from typing import Dict, Any
import asyncio
import subprocess
import os
import json
import atexit
import docker
from langchain_mcp_adapters.client import MultiServerMCPClient


container_names = ["mcp-sequential", "mcp-desktop-commander", "mcp-context7", "mcp-serena"]


class MCPManager:
    """Simple MCP server manager with Docker container support."""
    
    def __init__(self, config_path: str = "mcp.json"):
        self.config_path = config_path
        self.server_processes = {}
        self.clients = {}
        self.tools = {}
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self.docker_client = None
        self.global_settings = {}
        
        try:
            self.docker_client = docker.from_env()
            print("[MCP] Docker direct connection mode enabled")
        except Exception as e:
            print(f"[MCP] Failed to connect to Docker: {e}")
            raise
        
        atexit.register(self.stop_all_servers)
    
    async def load_config(self) -> Dict[str, Any]:
        """Load MCP configuration."""
        try:
            # Use default local config
            possible_paths = [
                self.config_path,
                f"../../{self.config_path}",
                f"/home/ysu1516/LangGraph/AutoDRP/{self.config_path}"
            ]
            
            for path in possible_paths:
                if await asyncio.to_thread(os.path.exists, path):
                    def read_json(file_path):
                        with open(file_path, 'r') as f:
                            return json.load(f)
                    
                    config = await asyncio.to_thread(read_json, path)
                    print(f"[MCP] Loaded config from: {path}")
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
                
                return await self._initialize_container_servers(config)
                
            except Exception as e:
                print(f"[MCP] Initialization failed: {e}")
                raise
    
    async def _initialize_container_servers(self, config: Dict[str, Any]):
        """Initialize MCP servers using direct container connections."""
        try:
            # Store global settings for use in connection methods
            self.global_settings = config.get("settings", {})
            
            # Wait for containers to be ready
            await self._wait_for_containers()
            
            # Connect to containerized servers
            for server_name, server_config in config["servers"].items():
                if not server_config.get("enabled", True):
                    continue
                
                tools = await self._connect_container_server(server_name, server_config)
                self.tools[server_name] = tools
            
            self._initialized = True
            print("[MCP] All container servers initialized")
            return self.tools
            
        except Exception as e:
            print(f"[MCP] Container initialization failed: {e}")
            raise
    
    
    async def _wait_for_containers(self):
        """Wait for MCP containers to be ready."""
        if not self.docker_client:
            return
            
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
    
    async def _connect_container_server(self, server_name: str, server_config: Dict[str, Any]):
        """Connect to a containerized MCP server."""
        try:
            # Get container configuration from server config
            container_name = server_config.get("container_name")
            if not container_name:
                print(f"[MCP] No container_name specified for {server_name}")
                return []
            
            # Check if container is running
            if not self._is_container_running(container_name):
                print(f"[MCP] Container {container_name} is not running")
                return []
            
            # Build docker exec command from configuration
            command = server_config.get("command", "node")
            args = server_config.get("args", ["dist/index.js"])
            transport = server_config.get("transport", "stdio")
            
            docker_args = ["exec", "-i", container_name, command] + args
            
            client_config = {
                server_name: {
                    "command": "docker",
                    "args": docker_args,
                    "transport": transport
                }
            }
            
            # Create MCP client and get real tools
            client = MultiServerMCPClient(client_config)
            self.clients[server_name] = client
            
            # Get real MCP tools from the server with timeout
            try:
                # Use timeout from global settings
                timeout = float(self.global_settings.get("connection_timeout", 15))
                tools = await asyncio.wait_for(client.get_tools(), timeout=timeout)
                print(f"[MCP] Connected to container {container_name}: {len(tools)} tools")
                return tools
            except asyncio.TimeoutError:
                print(f"[MCP] Connection to {container_name} timed out after {timeout} seconds")
                return []
            except Exception as conn_error:
                print(f"[MCP] Connection error for {server_name}: {conn_error}")
                return []
            
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