"""Simplified MCP server management."""

from typing import Dict, Any
import asyncio
import subprocess
import os
import json
import atexit
from langchain_mcp_adapters.client import MultiServerMCPClient


class MCPManager:
    """Simple MCP server manager."""
    
    def __init__(self, config_path: str = "mcp.json"):
        self.config_path = config_path
        self.server_processes = {}
        self.clients = {}
        self.tools = {}
        self._initialized = False
        self._init_lock = asyncio.Lock()
        atexit.register(self.stop_all_servers)
    
    async def load_config(self) -> Dict[str, Any]:
        """Load MCP configuration."""
        try:
            possible_paths = [
                self.config_path,
                f"../../{self.config_path}"
            ]
            
            for path in possible_paths:
                if await asyncio.to_thread(os.path.exists, path):
                    def read_json(file_path):
                        with open(file_path, 'r') as f:
                            return json.load(f)
                    
                    config = await asyncio.to_thread(read_json, path)
                    print(f"[MCP] Loaded config from: {path}")
                    return config
            
            raise FileNotFoundError("mcp.json not found")
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
                print("[MCP] All servers initialized")
                return self.tools
                
            except Exception as e:
                print(f"[MCP] Initialization failed: {e}")
                raise
    
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