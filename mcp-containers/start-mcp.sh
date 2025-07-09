#!/bin/bash

# Load environment variables from .env
source "$(dirname "$0")/../.env"

# MCP 환경 시작 스크립트 (4 MCP 서버)
echo "🚀 Starting MCP environment..."
echo "📁 Using PROJECT_ROOT: $PROJECT_ROOT"

echo "🧹 Cleaning up existing containers..."
docker stop mcp-sequential mcp-desktop-commander mcp-serena mcp-context7 2>/dev/null || true
docker rm mcp-sequential mcp-desktop-commander mcp-serena mcp-context7 2>/dev/null || true

echo "🧠 Starting sequential thinking server..."
docker run -d --name mcp-sequential --restart unless-stopped \
  -i -t mcp/sequentialthinking

echo "🖥️ Starting desktop commander server..."
docker run -d --name mcp-desktop-commander --restart unless-stopped \
  -v $PROJECT_ROOT:/workspace -i -t mcp/desktop-commander

echo "📚 Starting context7 server..."
docker run -d --name mcp-context7 --restart unless-stopped \
  -e MCP_TRANSPORT=stdio -i -t mcp/context7

echo "🔍 Starting Serena server..."
docker run -d --name mcp-serena --restart unless-stopped \
  -v $PROJECT_ROOT:/workspace \
  -e SERENA_DOCKER=1 -e SERENA_PORT=9121 -e SERENA_DASHBOARD_PORT=24283 -i -t \
  ghcr.io/oraios/serena:latest .venv/bin/serena-mcp-server --transport stdio --project AutoDRP

# Serena 컨테이너 패키지 설치
echo "📦 Installing data science packages in Serena container..."
sleep 8  # 컨테이너 완전 시작 대기

if [ -f "$PROJECT_ROOT/requirements_preprocessing.txt" ]; then
    echo "📋 Found requirements_preprocessing.txt, installing packages..."
    
    # Step 1: Install pip if not available
    echo "🔧 Ensuring pip is available in virtual environment..."
    docker exec mcp-serena python -m ensurepip --upgrade
    if [ $? -eq 0 ]; then
        echo "✅ pip installed/upgraded successfully"
    else
        echo "❌ Failed to install pip"
        docker logs mcp-serena --tail 10
        exit 1
    fi
    
    # Step 2: Install packages from requirements
    echo "📦 Installing data science packages..."
    docker exec mcp-serena python -m pip install -r /workspace/requirements_preprocessing.txt
    if [ $? -eq 0 ]; then
        echo "✅ Data science packages installed successfully in Serena container"
    else
        echo "❌ Failed to install packages in Serena container"
        docker logs mcp-serena --tail 60
    fi
else
    echo "⚠️ requirements_preprocessing.txt not found, skipping package installation"
fi

# 컨테이너 상태 확인
echo "📋 Checking container status..."
sleep 3
docker ps --filter "name=mcp-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "🔍 Running health checks..."
containers=("mcp-sequential" "mcp-desktop-commander" "mcp-serena" "mcp-context7")
names=("Sequential thinking" "Desktop commander" "Serena" "Context7")

for i in "${!containers[@]}"; do
    if docker ps --filter "name=${containers[$i]}" --filter "status=running" | grep -q "${containers[$i]}"; then
        echo "✅ ${names[$i]} server is running"
    else
        echo "❌ ${names[$i]} server failed to start"
        docker logs "${containers[$i]}" --tail 5
    fi
done
echo "🎉 MCP environment startup complete!"
echo "📝 All MCP servers running on stdio transport"
echo "📝 Use 'docker logs [container-name]' to check individual logs"
echo "🛑 Use './scripts/stop-mcp.sh' to stop all MCP services"