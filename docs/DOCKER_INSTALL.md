# Docker Desktop 安装指南

> 本指南帮助你在 macOS（及 Linux）上安装并配置 Docker Desktop，使其能够运行本项目的 `{{MCP_COUNT}}` 个 MCP 数据服务器容器（数字由 `scripts/count_mcp.py` 自动统计）。

---

## 一、为什么需要 Docker

本项目包含 **`{{MCP_COUNT}}` 个 MCP 数据服务器**（MicroContext Protocol），每个服务器对应一种数据类型或 API：

- **金融数据**: yfinance（美股）、tushare（A股）、eastmoney（研报）
- **宏观数据**: fed-data、wb-data、imf-data、oecd-data
- **学术数据**: openalex、arxiv、context7、semantic-scholar
- **工具服务**: pandas-mcp、playwright-mcp、filesystem-mcp

Docker 容器化确保：
1. **环境隔离** — 每个服务独立运行，不污染主机 Python 环境
2. **一致性** — 任何人在任何平台上获得完全相同的运行环境
3. **一键启动** — `./mcp_servers/start_all.sh` 启动所有服务

---

## 二、安装步骤

### 2.1 macOS 安装 Docker Desktop

#### 方法 A：Homebrew（推荐）

```bash
# 安装 Docker Desktop
brew install --cask docker

# 启动 Docker Desktop
open -a Docker
```

#### 方法 B：官方下载

1. 访问 [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
2. 下载 macOS 版本（Apple Silicon 或 Intel）
3. 将 `Docker.dmg` 拖入 Applications
4. 双击启动 Docker Desktop

#### 方法 C：OrbStack（轻量替代，适用于 macOS）

```bash
# 使用 OrbStack 替代 Docker Desktop（更轻量、启动更快）
brew install --cask orbstack
```

> **OrbStack** 完全兼容 Docker Desktop，docker-compose 文件和命令完全通用。

### 2.2 Linux（Ubuntu/Debian）安装

```bash
# 1. 卸载旧版本
sudo apt-get remove docker docker-engine docker.io containerd runc

# 2. 安装依赖
sudo apt-get update
sudo apt-get install ca-certificates curl gnupg lsb-release

# 3. 添加 Docker GPG 密钥
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 4. 添加 Docker 仓库
echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. 安装 Docker
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 6. 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker

# 7. 将当前用户加入 docker 组（避免每次 sudo）
sudo usermod -aG docker $USER
newgrp docker
```

### 2.3 Windows (WSL2)

```powershell
# 1. 启用 WSL2
wsl --install

# 2. 下载 Docker Desktop for Windows
# https://www.docker.com/products/docker-desktop/

# 3. 安装后启用 WSL2 后端
# Docker Desktop → Settings → General → Enable "Use the WSL2 based engine"
```

---

## 三、安装后验证

```bash
# 1. 检查 Docker 是否运行
docker info

# 2. 检查 docker compose 版本
docker compose version
# 输出类似：Docker Compose version v2.24.0

# 3. 确认资源
docker system df
```

---

## 四、启动 MCP 服务器

### 4.1 一键启动所有服务

```bash
# 进入项目根目录
cd /path/to/论文-研报工作流

# 启动所有 MCP 服务器（首次会自动构建镜像，需几分钟）
./mcp_servers/start_all.sh --start
```

### 4.2 按组启动（节省资源）

```bash
# 仅启动金融数据服务（yfinance、eastmoney 等）
./mcp_servers/start_all.sh --group finance

# 仅启动宏观数据服务
./mcp_servers/start_all.sh --group macro

# 仅启动学术数据服务
./mcp_servers/start_all.sh --group academic

# 仅启动中国数据服务
./mcp_servers/start_all.sh --group china
```

### 4.3 其他常用操作

```bash
# 查看服务状态
./mcp_servers/start_all.sh --status

# 查看日志
./mcp_servers/start_all.sh --logs

# 健康检查
./mcp_servers/start_all.sh --health

# 停止所有服务
./mcp_servers/start_all.sh --stop

# 重启服务
./mcp_servers/start_all.sh --restart

# 拉取最新镜像
./mcp_servers/start_all.sh --pull

# 重新构建镜像（代码更新后）
./mcp_servers/start_all.sh --build
```

---

## 五、配置 API Key（可选）

部分 MCP 服务需要 API Key。配置方法：

```bash
# 1. 创建 .env.local 文件
cp .env.example .env.local

# 2. 编辑 .env.local，填入你的 API Key
nano .env.local

# 常用 Key：
# TUSHARE_TOKEN=your_tushare_token    # https://tushare.pro/register
# EODHD_API_KEY=your_eodhd_key       # https://eodhd.com/
# BRAVE_SEARCH_API_KEY=your_key       # https://brave.com/search/api/
```

> **注意**：大多数 MCP 服务无需 API Key 即可使用（yfinance、openalex、arxiv、fed-data 等均为免费接口）。

---

## 六、故障排除

### Docker Desktop 未运行

```bash
# macOS
open -a Docker

# 或检查状态
docker info 2>&1 | head -5
```

### 端口冲突

```bash
# 检查端口占用
lsof -i :8000 -i :8001 -i :8002

# 停止占用端口的进程
kill -9 <PID>
```

### 镜像构建失败

```bash
# 清理 Docker 缓存
docker system prune -a -f

# 重新构建
./mcp_servers/start_all.sh --build
```

### 容器无法启动

```bash
# 查看具体错误日志
docker compose logs -f <service_name>

# 例如：查看 tushare 服务日志
docker compose logs -f mcp_tushare
```

### Apple Silicon (M1/M2/M3) 兼容性问题

如果某些镜像不支持 arm64，在 `docker-compose.yml` 中为该服务添加：

```yaml
services:
  mcp_xxx:
    platform: linux/amd64   # 强制使用 amd64 兼容模式
    build:
      context: ./mcp_servers/user_xxx
```

---

## 七、资源要求

| 规格 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 内存 | 4 GB RAM | 8 GB RAM |
| CPU | 2 核 | 4 核 |
| 磁盘 | 20 GB | 50 GB |
| macOS | macOS 11+ | macOS 13+ |

> **提示**：如果机器内存较小，使用 `--group` 参数按需启动服务组，而非全部启动。

---

## 八、常用 Docker 命令参考

```bash
# 进入容器内调试
docker compose exec mcp_yfinance bash

# 查看容器资源使用
docker stats

# 查看所有镜像
docker images

# 删除未使用镜像
docker image prune -a -f

# 查看 Docker 磁盘占用
docker system df

# 完全清理（包括停止的容器、未使用的网络）
docker system prune -f
```
