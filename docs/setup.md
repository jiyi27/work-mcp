# 配置、启动与部署

本文档说明如何初始化 `work-mcp`，以及如何按两种运行方式部署：

- 本地 `stdio` 模式：给本机 MCP 客户端直接拉起，默认只启用 `jira`
- 远程 HTTP 模式：部署在服务器上，通过 `/mcp` 提供服务，默认只启用 `database` 和 `log_search`

---

## 1. 安装

前置条件：安装 [uv](https://docs.astral.sh/uv/)

```bash
git clone <你的仓库地址> work-mcp
cd work-mcp
uv sync
```

### SQL Server 额外依赖

仅在启用 `database` 且数据库类型为 SQL Server 时需要安装 Microsoft ODBC Driver。

```bash
# macOS
brew install microsoft/mssql-release/msodbcsql18

# Ubuntu（18.04 / 20.04 / 22.04 / 24.04）
curl -sSL -O https://packages.microsoft.com/config/ubuntu/$(grep VERSION_ID /etc/os-release | cut -d '"' -f 2)/packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb && rm packages-microsoft-prod.deb
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18

# Debian（9 / 10 / 11 / 12 / 13）
curl -sSL -O https://packages.microsoft.com/config/debian/$(grep VERSION_ID /etc/os-release | cut -d '"' -f 2 | cut -d '.' -f 1)/packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb && rm packages-microsoft-prod.deb
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18

# RHEL / Oracle Linux（7 / 8 / 9 / 10）
curl -sSL -O https://packages.microsoft.com/config/rhel/$(grep VERSION_ID /etc/os-release | cut -d '"' -f 2 | cut -d '.' -f 1)/packages-microsoft-prod.rpm
sudo yum install packages-microsoft-prod.rpm && rm packages-microsoft-prod.rpm
sudo ACCEPT_EULA=Y yum install -y msodbcsql18
```

---

## 2. 初始化配置

运行：

```bash
make init
```

初始化向导会先问当前运行环境：

- `1. 远程服务器`
- `2. 本地`

两种模式的行为现在是固定的。

### 本地模式

本地模式会：

- 只启用 `jira`
- 自动移除 `database`、`log_search`、`dingtalk`
- 清理这些已移除插件对应的 `.env` 凭据和 `config.yaml` 配置段

向导会收集：

- `JIRA_BASE_URL`
- `JIRA_API_TOKEN`
- `JIRA_PROJECT_KEY`

生成结果：

- `.env`：保存 Jira 凭据
- `config.yaml`：只保留 `plugins.enabled: [jira]`，并写入 Jira 默认状态占位值

### 远程服务器模式

远程模式会：

- 只启用 `database` 和 `log_search`
- 自动移除 `jira`、`dingtalk`
- 清理这些已移除插件对应的 `.env` 凭据和 `config.yaml` 配置段

向导会收集：

- `database`：数据库类型、主机、端口、用户名、密码、默认数据库名、连接超时
- SQL Server 额外收集：`DB_DRIVER`
- `log_search`：日志根目录绝对路径

生成结果：

- `.env`：保存数据库凭据
- `config.yaml`：启用 `database` 和 `log_search`

---

## 3. 校准 Jira 工作流状态

仅在本地模式启用 `jira` 时需要这一步。

`make init` 会在 `config.yaml` 中写入默认占位值：

```yaml
jira:
  latest_assigned_statuses:
    - 重新打开
    - ToDo
  start_target_status: 已接受
  resolve_target_status: 已解决
  attachments:
    max_images: 5
    max_bytes_per_image: 1048576
```

这些值通常需要替换成你当前 Jira 项目里实际存在的状态名。

先查询实际状态：

```bash
uv run python scripts/inspect_jira_issue_workflow.py <ISSUE-KEY>
```

再修改 `config.yaml`：

```yaml
jira:
  latest_assigned_statuses:
    - 待处理
    - 处理中
  start_target_status: 处理中
  resolve_target_status: 已解决
```

状态名称必须与 Jira 工作流中的 status 名称完全一致。字段详细说明见 [`config.example.yaml`](../config.example.yaml)。

---

## 4. 验证配置

```bash
make doctor
```

输出每项检查结果：

- `[ok]`
- `[warn]`
- `[error]`

存在 `[error]` 时，服务无法正常启动，需要先修正配置。

---

## 5. 本地部署：stdio 模式

适用场景：

- 你的 MCP 客户端运行在本机
- 由客户端直接拉起 `work-mcp`
- 主要使用 Jira 工具

### 启动方式

```bash
uv run work-mcp
```

或：

```bash
make run-stdio
```

默认就是 `stdio` 模式。

### MCP 客户端配置示例

```json
{
  "mcpServers": {
    "work-mcp": {
      "command": "uv",
      "args": ["run", "work-mcp"],
      "cwd": "/absolute/path/to/work-mcp"
    }
  }
}
```

这类配置适用于会在本地直接启动 MCP 进程的客户端。

---

## 6. 远程部署：HTTP 模式

适用场景：

- `work-mcp` 部署在服务器
- 客户端通过网络访问
- 主要提供数据库查询和日志检索能力

### 启动方式

推荐直接使用：

```bash
make run
```

默认监听：

- `HOST=0.0.0.0`
- `PORT=8182`

也可以显式指定：

```bash
make run HOST=127.0.0.1 PORT=9000
```

对应的 MCP 端点为：

```text
http://<host>:<port>/mcp
```

例如：

```text
http://127.0.0.1:8182/mcp
```

### 直接用命令行启动

```bash
uv run work-mcp --transport streamable-http --host 0.0.0.0 --port 8182
```

如果你直接写：

```bash
uv run work-mcp --transport streamable-http
```

而没有传 `--host` 和 `--port`，代码里的默认值是：

- `127.0.0.1`
- `8000`

### 客户端接入

支持 Streamable HTTP 的 MCP 客户端，直接把服务地址指向：

```text
http://<server-host>:<port>/mcp
```

客户端具体配置格式取决于客户端本身，但目标地址就是这个 `/mcp` 端点。

---

## 7. 手动配置文件

如果不使用 `make init`，可以手动初始化：

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

然后按需编辑两个文件。

注意：

- `.env` 只放敏感凭据
- `config.yaml` 只放非敏感配置
- 如果你走本地模式，建议只保留 `jira`
- 如果你走远程模式，建议只保留 `database` 和 `log_search`

所有字段说明见 [`config.example.yaml`](../config.example.yaml)。
