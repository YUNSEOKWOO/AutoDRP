#!/bin/bash

# MCP 환경 상태 확인 스크립트
echo "📊 MCP Environment Status"
echo "=========================="

# 네트워크 상태
echo "🔗 Network Status:"
if docker network ls | grep -q mcp-network; then
    echo "✅ mcp-network exists"
    docker network inspect mcp-network --format="{{.Name}}: {{len .Containers}} containers connected"
else
    echo "❌ mcp-network not found"
fi
echo

# 컨테이너 상태
echo "📦 Container Status:"
if docker ps -a --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" | grep -q mcp-; then
    docker ps -a --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
else
    echo "❌ No MCP containers found"
fi
echo

# 포트 사용 상태
echo "🔌 Port Usage:"
netstat -tlnp 2>/dev/null | grep -E ":(8080|8081|8082)" || echo "No MCP ports in use"
echo

# 로그 요약 (최근 오류만)
echo "📝 Recent Logs (Errors only):"
for container in mcp-sequential mcp-filesystem; do
    if docker ps --filter "name=$container" --filter "status=running" | grep -q $container; then
        echo "--- $container (last 5 error lines) ---"
        docker logs $container 2>&1 | grep -i error | tail -5 || echo "No errors found"
    fi
done
echo

# 리소스 사용량
echo "💾 Resource Usage:"
if docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | grep -q mcp-; then
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep mcp-
else
    echo "No running MCP containers to show stats"
fi
echo

# 헬스체크 요약
echo "🔍 Health Summary:"
running_count=$(docker ps --filter "name=mcp-" --filter "status=running" | wc -l)
total_count=$(docker ps -a --filter "name=mcp-" | wc -l)

if [ $running_count -eq 0 ]; then
    echo "❌ No MCP containers are running"
elif [ $running_count -eq 2 ]; then
    echo "✅ All MCP services are running ($running_count/2)"
else
    echo "⚠️  Some MCP services are not running ($running_count/2)"
fi

echo "=========================="
echo "🔧 Available commands:"
echo "  ./scripts/start-mcp.sh  - Start MCP environment"
echo "  ./scripts/stop-mcp.sh   - Stop MCP environment"
echo "  docker logs mcp-[name]  - View specific container logs"