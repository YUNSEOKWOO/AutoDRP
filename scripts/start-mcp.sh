#!/bin/bash

# MCP 환경 시작 스크립트
echo "🚀 Starting MCP environment..."

# 네트워크 생성 (이미 존재하면 무시)
echo "📡 Creating MCP network..."
docker network create mcp-network 2>/dev/null || echo "Network already exists"

# 기존 컨테이너 정리
echo "🧹 Cleaning up existing containers..."
docker stop mcp-sequential 2>/dev/null || true
docker rm mcp-sequential 2>/dev/null || true
docker stop mcp-desktop-commander 2>/dev/null || true
docker rm mcp-desktop-commander 2>/dev/null || true

# Sequential thinking 서버 시작
echo "🧠 Starting sequential thinking server..."
docker run -d \
  --name mcp-sequential \
  --network mcp-network \
  --restart unless-stopped \
  -i -t \
  mcp/sequentialthinking

# Desktop commander 서버 시작
echo "🖥️ Starting desktop commander server..."
docker run -d \
  --name mcp-desktop-commander \
  --network mcp-network \
  --restart unless-stopped \
  -i -t \
  mcp/desktop-commander

# 컨테이너 상태 확인
echo "📋 Checking container status..."
sleep 3
docker ps --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 헬스체크
echo "🔍 Running health checks..."
if docker ps --filter "name=mcp-sequential" --filter "status=running" | grep -q mcp-sequential; then
    echo "✅ Sequential thinking server is running"
else
    echo "❌ Sequential thinking server failed to start"
    docker logs mcp-sequential --tail 10
fi

if docker ps --filter "name=mcp-desktop-commander" --filter "status=running" | grep -q mcp-desktop-commander; then
    echo "✅ Desktop commander server is running"
else
    echo "❌ Desktop commander server failed to start"
    docker logs mcp-desktop-commander --tail 10
fi

echo "🎉 MCP environment startup complete!"
echo "📝 Use 'docker logs mcp-sequential' to check logs"
echo "🛑 Use './scripts/stop-mcp.sh' to stop all MCP services"