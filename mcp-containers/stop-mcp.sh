#!/bin/bash

# Load environment variables from .env
source "$(dirname "$0")/../.env"

# MCP 환경 정지 스크립트
echo "🛑 Stopping MCP environment..."
echo "📋 MCP Names: $MCP_NAMES"

# MCP 컨테이너들 정지
echo "⏹️  Stopping MCP containers..."
docker stop $MCP_NAMES 2>/dev/null || echo "Some containers were not running"

# 컨테이너 제거
echo "🗑️  Removing MCP containers..."
docker rm $MCP_NAMES 2>/dev/null || echo "Some containers were already removed"

# 최종 상태 확인
echo "📋 Final status check..."
if docker ps -a --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}" | grep -q mcp-; then
    echo "⚠️  Some MCP containers still exist:"
    docker ps -a --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}"
else
    echo "✅ All MCP containers have been removed"
fi

echo "🎉 MCP environment cleanup complete!"