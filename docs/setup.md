# 配置与部署

`work-mcp` 现在有两种推荐运行方式

- 本地模式: 只启用 `jira`, 通过 `stdio` 由 MCP 客户端直接拉起本地子进程
- 远程模式: 只启用 `database` 和 `log_search`, 通过 HTTP 暴露 `/mcp` 端点给客户端连接

## 1. 安装

前置条件:需要先安装 python 包管理器 [uv](https://docs.astral.sh/uv/)

```bash
git clone <你的仓库地址> work-mcp
cd work-mcp
uv sync
```

## 2. 初始化配置

运行

```bash
make init
```

向导会先问当前运行环境

- `1. 远程服务器`
- `2. 本地`

当前行为是固定的

- 选择"本地"后, 只保留 `jira`
- 选择"远程服务器"后, 只保留 `database` 和 `log_search`

同时, 向导会清理不属于当前模式的旧插件配置和对应凭据

## 3. 连接客户端

### 3.1. 本地模式

本地模式推荐使用 `stdio`, 原因是客户端和 `work-mcp` 在同一台机器上时, 客户端可以直接启动本地子进程, 不需要额外开放 HTTP 端口

客户端配置示例

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

配置完成后, 客户端会自动拉起 `work-mcp`, 通常不需要你手动启动 mcp server

### 3.2. 远程模式

远程模式需要使用 HTTP, 原因是 `stdio` 依赖客户端直接在本机拉起子进程, 而远程服务器无法用这种方式把标准输入输出直接交给客户端

服务端启动

```bash
make run
```

默认监听

- `0.0.0.0:8182`

MCP 端点

```text
http://<server-host>:8182/mcp
```

如果要改地址

```bash
make run HOST=127.0.0.1 PORT=9000
```

然后让支持 Streamable HTTP 的 MCP 客户端连接

```text
http://<server-host>:<port>/mcp
```

## 4. 验证配置

运行

```bash
make doctor
```

输出会包含

- `[ok]`
- `[warn]`
- `[error]`

有 `[error]` 时, 先修正配置再启动服务

## 5. 补充说明

### 5.1. Jira 状态校准

本地模式启用 `jira` 后, `make init` 会先写入一组默认占位值, 通常你还需要根据自己项目的实际工作流状态修改 `config.yaml`

先查询

```bash
uv run python scripts/inspect_jira_issue_workflow.py <ISSUE-KEY>
```

再按输出结果调整 `jira.latest_assigned_statuses`, `jira.start_target_status`, `jira.resolve_target_status`

### 5.2. SQL Server 依赖

如果远程模式使用 SQL Server, 需要先在主机上安装 ODBC Driver 18 for SQL Server, 字段和示例见 [`config.example.yaml`](../config.example.yaml)

### 5.3. 手动配置文件

如果不使用 `make init`, 可以手动初始化

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

- `.env` 只放敏感凭据
- `config.yaml` 只放非敏感配置

所有字段说明见 [`config.example.yaml`](../config.example.yaml)
