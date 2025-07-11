"""Simplified MCP server management."""

from typing import Dict, Any
import asyncio
import subprocess
import os
import json
import atexit
import docker
from langchain_mcp_adapters.client import MultiServerMCPClient


# .env에서 MCP 목록 가져옴.
container_names = os.getenv('MCP_NAMES', '').split()

def load_mcp_config(config_path: str = "mcp.json") -> Dict[str, Any]:
    """Load MCP configuration from JSON file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[MCP] Failed to load config from {config_path}: {e}")
        return {"servers": {}, "settings": {}}


class MCPManager:
    """Simple MCP server manager with Docker container support."""
    
    def __init__(self):
        self.clients = {}
        self.tools = {}
        self._initialized = False
        self.docker_client = None
        self.config = load_mcp_config()
        
        try:
            self.docker_client = docker.from_env()
            print("[MCP] Docker direct connection mode enabled")
        except Exception as e:
            print(f"[MCP] Failed to connect to Docker: {e}")
            raise
        
        atexit.register(self.stop_all_servers)
    
    
    async def initialize_all_servers(self):
        """Initialize all MCP servers."""
        if self._initialized:
            return self.tools
        
        try:
            print("[MCP] Starting server initialization...")
            
            # Wait for containers to be ready
            await self._wait_for_containers()
            
            # Connect to all container servers
            for container_name in container_names:
                if not container_name:
                    continue
                
                tools = await self._connect_container_server(container_name)
                self.tools[container_name] = tools
            
            self._initialized = True
            print("[MCP] All container servers initialized")
            return self.tools
            
        except Exception as e:
            print(f"[MCP] Initialization failed: {e}")
            raise
    
    
    async def _wait_for_containers(self):
        """Wait for MCP containers to be ready."""
        if not self.docker_client or not container_names:
            return
            
        try:
            running_containers = []
            for name in container_names:
                if self._is_container_running(name):
                    running_containers.append(name)
            
            if running_containers:
                print(f"[MCP] Found running containers: {running_containers}")
            else:
                print("[MCP] Warning: No MCP containers found running")
                
        except Exception as e:
            print(f"[MCP] Error checking containers: {e}")
    
    async def _connect_container_server(self, container_name: str):
        """Connect to a containerized MCP server."""
        try:
            # Check if container is running
            if not self._is_container_running(container_name):
                print(f"[MCP] Container {container_name} is not running")
                return []
            
            # Get server configuration from mcp.json
            # Extract base name from container name (remove USER_ID suffix)
            base_name = container_name
            user_id = os.getenv('USER_ID', '').strip()
            if user_id and container_name.endswith(f'_{user_id}'):
                base_name = container_name[:-len(f'_{user_id}')]
            
            server_config = self.config.get("servers", {}).get(base_name, {})
            if not server_config:
                print(f"[MCP] No configuration found for {base_name} (container: {container_name})")
                return []
            
            # Build docker exec command from configuration
            command = server_config.get("command", "node")
            args = server_config.get("args", ["dist/index.js"])
            docker_args = ["exec", "-i", container_name, command] + args
            
            client_config = {
                container_name: {
                    "command": "docker",
                    "args": docker_args,
                    "transport": server_config.get("transport", "stdio")
                }
            }
            
            # Create MCP client and get real tools
            client = MultiServerMCPClient(client_config)
            self.clients[container_name] = client
            
            # Get real MCP tools from the server with timeout
            try:
                timeout = self.config.get("settings", {}).get("connection_timeout", 15)
                tools = await asyncio.wait_for(client.get_tools(), timeout=timeout)
                print(f"[MCP] Connected to container {container_name}: {len(tools)} tools")
                return tools
            except asyncio.TimeoutError:
                print(f"[MCP] Connection to {container_name} timed out after {timeout} seconds")
                return []
            except Exception as conn_error:
                print(f"[MCP] Connection error for {container_name}: {conn_error}")
                return []
            
        except Exception as e:
            print(f"[MCP] Failed to connect to container {container_name}: {e}")
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
    
    
    def stop_all_servers(self):
        """Stop all server connections."""
        # Note: Docker containers are managed externally
        # This only cleans up client connections
        self.clients.clear()
        self.tools.clear()
        self._initialized = False
        print("[MCP] Cleared all server connections")