#!/bin/bash

# MCP 환경 정지 스크립트
echo "🛑 Stopping MCP environment..."

# MCP 컨테이너들 정지
echo "⏹️  Stopping MCP containers..."
docker stop mcp-sequential mcp-desktop-commander mcp-serena mcp-context7 2>/dev/null || echo "Some containers were not running"

# 컨테이너 제거
echo "🗑️  Removing MCP containers..."
docker rm mcp-sequential mcp-desktop-commander mcp-serena mcp-context7 2>/dev/null || echo "Some containers were already removed"

# 최종 상태 확인
echo "📋 Final status check..."
if docker ps -a --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}" | grep -q mcp-; then
    echo "⚠️  Some MCP containers still exist:"
    docker ps -a --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}"
else
    echo "✅ All MCP containers have been removed"
fi

echo "🎉 MCP environment cleanup complete!"