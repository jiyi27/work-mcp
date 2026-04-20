这份文档按步骤说明如何把 `work-mcp` 配起来并启动

如果你只想查某个字段的详细含义, 再看 [README.md](../README.md)

## 1. 准备环境

先安装 `uv`, 然后在仓库根目录安装依赖

```bash
uv sync
```

**Linux 上需要额外安装系统依赖**

项目依赖 `pyodbc`, 它在启动时会链接系统的 `libodbc.so.2`, 不管你用 MySQL 还是 SQL Server 都需要装

RHEL / CentOS:

```bash
sudo dnf install -y unixODBC
```

Ubuntu / Debian:

```bash
sudo apt-get install -y unixodbc
```

如果服务器没有外网, 用 `--disablerepo=epel` 等方式跳过无法访问的源:

```bash
sudo dnf install -y unixODBC --disablerepo=epel
```

如果你要启用 SQL Server 数据库插件, 还需要额外安装 `ODBC Driver 18 for SQL Server`

## 2. 创建配置文件

如果还没有配置文件, 先复制一份模板

```bash
cp config.example.yaml config.yaml
```

后面的配置都写在 `config.yaml` 里, 直接手动编辑即可, 不需要再跑单独的初始化向导

## 3. 选择要启用的插件

先在 `plugins.enabled` 里写上这次启动要使用的工具组, 然后只配置这些工具组对应的内容就行, 没启用的插件可以先不管

示例

```yaml
plugins:
  enabled:
    - jira
    - remote_fs
    - database
    - dingtalk
```

上面这份配置表示: 启动时只启用 `jira` 和 `remote_fs`

## 4. 按需配置插件

下面这些小节都是可选的

- 如果不启用某个插件, 可以不配这一节
- 如果启用了某个插件, 就要把对应配置补完整

### 4.1. Jira

适合本地开发机使用, 也适合只想处理 Jira 工单的场景

```yaml
plugins:
  enabled:
    - jira

jira:
  base_url: https://your-jira-instance.example.com
  api_token: your_jira_api_token_here
  project_key: PROJECT1
  latest_assigned_statuses:
    - 待处理
    - 已接收
    - 处理中
  start_target_status: 已接收
  resolve_target_status: 已解决
  attachments:
    max_images: 5
    max_bytes_per_image: 1048576
```

- `base_url` 是 Jira 地址
- `api_token` 是 Jira token
- `project_key` 是允许操作的项目 key
- `latest_assigned_statuses` 是 `jira_list_open_assigned_issues` 会列出的状态
- `start_target_status` 和 `resolve_target_status` 是开始处理, 完成处理时要切换到的目标状态

如果你不确定状态名, 可以先运行

```bash
uv run python scripts/inspect_jira_issue_workflow.py YOUR-123
```

### 4.2. Database

用于只读查询线上数据库, 建议使用只读账号

MySQL 示例

```yaml
plugins:
  enabled:
    - database

database:
  type: mysql
  host: your-mysql-host.example.com
  port: 3306
  user: readonly_user
  password: your_password_here
  connect_timeout_seconds: 5
```

SQL Server 示例

```yaml
plugins:
  enabled:
    - database

database:
  type: sqlserver
  host: your-sqlserver-host.example.com
  port: 1433
  user: readonly_user
  password: your_password_here
  driver: ODBC Driver 18 for SQL Server
  trust_server_certificate: true
  connect_timeout_seconds: 5
```

- `type` 填 `mysql` 或 `sqlserver`
- `user` 应该是只读账号
- SQL Server 需要 `driver`, 并且要和机器上实际安装的驱动名称一致
- MySQL 不需要 `driver`

### 4.3. Remote FS

用于查看远程机器上的只读目录, 比如日志, 运行时配置, 部署目录

```yaml
plugins:
  enabled:
    - remote_fs

remote_fs:
  roots:
    - name: app
      path: /srv/myapp
      description: Deployed application source

    - name: logs
      path: /var/log/myapp
      description: Application log files

    - name: config
      path: /etc/myapp
      description: Production configuration
```

- `roots` 里每一项都是一个允许访问的根目录
- `name` 是给 agent 看的短名字
- `path` 必须是服务器上真实存在的目录
- `description` 主要是帮助 agent 理解这个目录是干什么的

### 4.4. DingTalk

用于发送钉钉通知

```yaml
plugins:
  enabled:
    - dingtalk

dingtalk:
  webhook_url: https://oapi.dingtalk.com/robot/send?access_token=your_token_here
  secret: SECxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- `webhook_url` 必填
- `secret` 只在机器人开启签名校验时需要, 不启用的话可以不填

## 5. 补充通用配置

日志配置是可选的, 不写也可以启动

```yaml
logging:
  dir: logs
  level: info
```

- `dir` 是日志目录
- `level` 可选 `debug`, `info`, `warning`, `error`

## 6. 检查配置

启动前先检查一次

```bash
make check
```

`make check` 的作用

- 检查 `config.yaml` 是否完整
- 检查当前启用插件的必要连通性
- 只检查 `plugins.enabled` 里已经启用的插件

## 7. 启动服务

最常用的是

```bash
make run
```

`make run` 会以 HTTP 模式启动 MCP 服务, 默认监听

```text
http://0.0.0.0:8182/mcp
```

如果要改地址或端口

```bash
make run HOST=127.0.0.1 PORT=9000
```
