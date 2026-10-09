# Mac mini + Tailscale 部署

在 Mini 上运行 Python 后端与 IB Gateway，iOS App 通过 Tailnet 私有 HTTPS 访问。
首次部署（包括 Docker 与 Xcode）以[主 README](../README.md)为入口。本页保留
LaunchAgent、维护与旧网页访问说明。下面使用占位符，不包含账户、设备 IP 或密码。

## 1. 本机安装

准备 Python 3.10+、Git、Docker Desktop（若 Gateway 在容器中）和 Tailscale。

```sh
mkdir -p "$HOME/Projects"
cd "$HOME/Projects"
git clone https://github.com/WahBun/AllYouNeedIsWheel.git
cd AllYouNeedIsWheel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp connection.json.example connection.json
```

下载慢时可改用镜像：

```sh
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120
```

编辑本机 `connection.json`：host 为 `127.0.0.1`，Gateway 实盘通常为 4001、
模拟盘通常为 4002，填写明确的 account_id，并使用固定且不冲突的 client_id。
先保持 `readonly: true` 验证读取；确认需要交易后才改为 false。
文件名不决定实盘/模拟盘，实际 Gateway 会话和配置才决定。

配置、数据库、日志和虚拟环境被 Git 忽略，不要强制加入提交。不要复制示例中的
`YOUR_ACCOUNT_ID` 作为真实账户。Gateway 容器只需把 API 端口映射到本机回环地址。

```sh
python run_api.py
curl http://127.0.0.1:8000/health
```

先确认 `http://127.0.0.1:8000` 的页面和账户数据正常，再配置远程访问。

## 2. Tailnet 私有访问

Mini 和访问设备登录同一 Tailnet，并在访问策略中允许这些可信设备访问 Mini。

```sh
tailscale ip -4
tailscale serve status
tailscale serve --bg --tcp=8000 tcp://127.0.0.1:8000
```

在 MacBook 或手机打开 `http://<Mini 的 Tailscale IPv4>:8000`。
这里使用 TCP 转发，以支持直接输入 IP；HTTP Serve 的域名匹配可能让 IP 访问
返回 404。`--bg` 将转发保存到 Tailscale 配置，Tailscale 重启后仍可恢复。

Web 服务仍只绑定 `127.0.0.1:8000`，通过 Tailnet 转发访问。不需要路由器公网
端口转发，也不要启用 Tailscale Funnel。页面采用 HTTP，但设备间连接由
Tailscale 加密；浏览器地址栏仍可能显示非 HTTPS 提示。

不要执行 `tailscale serve reset`，以免清除其他已有转发；也无需修改 Gateway
安全设置或增加 Gateway 的远程暴露。

```sh
curl http://<Mini 的 Tailscale IPv4>:8000/health
tailscale serve status
# 只关闭网页版的 Tailnet 转发：
tailscale serve --tcp=8000 off
```

出门前用手机关闭 Wi-Fi、走蜂窝网络测试页面和持仓读取。

### 推荐：私有 HTTPS 与 iPhone 主屏幕

原生 iOS App 必须使用 HTTPS；前面的 IP/TCP 入口仅适用于旧网页初期验证或临时备用。
先确认 MagicDNS 已开启，在 Tailscale 管理页面授权 Serve/HTTPS；不要开启 Funnel。

```sh
tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
curl https://<设备名>.<Tailnet后缀>/health
```

使用 Serve 输出的完整 HTTPS 地址，不要照抄其他人的后缀。证书首次签发可能
需要等待，验证时不要跳过证书检查。HTTPS 证书中的设备域名会进入公开证书
透明度日志，因此域名不要包含私人信息。访问权限仍由 Tailnet 策略控制。

手机与电脑验证新地址后，可只关闭旧的远程 HTTP 入口：

```sh
tailscale serve --tcp=8000 off
```

这不会停止本机 `127.0.0.1:8000`，HTTPS 仍代理到该服务。保留其他已有转发，
不要执行全局 reset。后台 Serve 配置持久保存，仍依赖 Tailscale 在线。

在 iPhone Safari 打开 HTTPS 地址，刷新后选择“添加到主屏幕”。项目提供
Manifest、现有图标和 iOS standalone 标签。旧快捷图标需要删除并重新添加；
正常情况下从图标进入独立窗口，不再重复创建普通浏览器标签。系统回收后台后
仍可能重新加载。这里没有增加 Service Worker、离线行情缓存或交易请求重试。
更换访问地址或使用独立窗口后，应检查语言、主题及下单确认偏好；账户与订单
仍来自同一个服务。不要将主屏幕安装视为身份认证或原生 App 发布。

## 3. macOS 登录后自启动

使用 LaunchAgent，保存为
`~/Library/LaunchAgents/com.wahbun.allyouneediswheel.plist`。
将以下所有 `/ABSOLUTE/PROJECT` 替换为本机项目绝对路径；plist 不展开 `~`。
先创建项目的 `logs` 目录，停止此前手动启动的同一服务，再加载。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.wahbun.allyouneediswheel</string>
  <key>WorkingDirectory</key><string>/ABSOLUTE/PROJECT</string>
  <key>ProgramArguments</key><array>
    <string>/ABSOLUTE/PROJECT/.venv/bin/gunicorn</string>
    <string>--workers=1</string>
    <string>--worker-class=gthread</string>
    <string>--threads=8</string>
    <string>--bind=127.0.0.1:8000</string>
    <string>--pid=logs/web.pid</string>
    <string>--access-logfile=logs/web-access.log</string>
    <string>--error-logfile=logs/web-error.log</string>
    <string>app:app</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/ABSOLUTE/PROJECT/logs/launchd-out.log</string>
  <key>StandardErrorPath</key><string>/ABSOLUTE/PROJECT/logs/launchd-error.log</string>
</dict></plist>
```

```sh
mkdir -p logs
plutil -lint "$HOME/Library/LaunchAgents/com.wahbun.allyouneediswheel.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.wahbun.allyouneediswheel.plist"
# 查看状态：
launchctl print "gui/$(id -u)/com.wahbun.allyouneediswheel"
# 优雅退出后由 KeepAlive 重启：
launchctl kill SIGTERM "gui/$(id -u)/com.wahbun.allyouneediswheel"
# 停止到下次登录或手动 bootstrap：
launchctl bootout "gui/$(id -u)/com.wahbun.allyouneediswheel"
```

刚 bootout 后应等待旧进程退出、8000 释放，再 bootstrap。修改 plist 后须重新
加载；只修改代码可以用上面的 SIGTERM 重启。不要在订单正在提交时主动重启。

这是用户登录后启动，不是登录前的系统服务。重启后的 FileVault 解锁、用户登录、
Docker Desktop/Tailscale 自启动及 Gateway 登录仍需分别保证。Mini 不应进入系统
休眠；显示器可以关闭。Gateway 容器的重启策略不能替代 Docker Desktop 的启动。

## 4. 更新与排错

更新前检查 `git status`，保留本机改动；干净工作区可用 `git pull --ff-only`。
依赖变化时在虚拟环境内重新安装 requirements，运行项目测试，再重启服务。
不要用 reset/覆盖配置来解决更新冲突。

- 本机也打不开：查看 LaunchAgent 状态、`logs/web-error.log` 和 8000 监听。
- 本机正常、远端失败：检查两端 Tailscale 在线状态、Serve 配置和 Tailnet 策略。
- 页面正常、数据不可用：检查 Gateway 登录、账户配置、行情订阅和连接日志。
- HTTP 503 / Retry-After：IB 请求队列已满，等待后重试；不要自动重发交易请求。
- 初次报价慢：合约确认和首次订阅可能耗时数秒；热查询通常更快。

单进程、八个 HTTP 线程依赖项目内的专用 API 执行线程。不要通过增加 Gunicorn
进程数或删除调度器来加速，否则会破坏 IB 连接身份与订单状态一致性。

## Docker 故障自动恢复（可选）

`ops/docker_watchdog.py` 是 Mini 本地 LaunchAgent，不依赖 Codex 对话保持打开。
每 60 秒通过 Docker Unix socket 检查一次 `_ping`，连续 3 次失败才尝试恢复。
正常 Docker 不会定时重启；行情为空、休市、IB 登录等待或 Wheel HTTP 503 本身
都不会触发 Docker 重启。每次恢复间隔至少 30 分钟，滚动 24 小时最多 2 次。

恢复前只读检查本地订单数据库。有 submitting、unknown、canceling 或未确认改单，
或者数据库不可读时，暂停自动恢复并在 Mini 通知。已在券商挂单的 processing
订单不会由看护程序修改或撤销；本地检查不能证明券商端没有未同步的交易。

先尝试 Docker 官方 restart；45 秒不能退出时，终止 Docker.app 包内的进程，
再打开 Docker。此操作会中断所有 Docker 容器，不能用于还承担其他关键容器的机器，
除非已经接受这个范围。不会删除镜像、容器、卷、Gateway 配置或订单数据库。
Gateway 登录可能需要 IB Key；不要假设通知一定会自动到手机。

恢复后验证 Wheel bootstrap 的账户数据读取，必要时仅重启一次 Wheel 后端。
若 Gateway 尚未登录，记录等待状态，不循环重启。系统通知仅在 Mini 上显示；
不提供 iPhone 故障推送。账户数据恢复也不代表已验证所有行情订阅。

安装前先将 Pro 修改提交推送 GitHub，再在 Mini 拉取。以下仅在 Mini 项目目录运行：

```sh
.venv/bin/python ops/docker_watchdog.py --project "$PWD" \
  --state-dir "$HOME/Library/Application Support/Wheel/DockerWatchdog" --check-only
.venv/bin/python ops/install_docker_watchdog.py --project "$PWD"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.wahbun.wheel.docker-watchdog.plist"
launchctl print "gui/$(id -u)/com.wahbun.wheel.docker-watchdog"
```

用户登录后自动运行；关机、断电、休眠或尚未登录时无法工作。状态计数保存在
`~/Library/Application Support/Wheel/DockerWatchdog/state.json`，重启看护不会清空
冷却计数。日志在 `logs/docker-watchdog*.log`。手动维护 Docker 前暂停看护：

```sh
launchctl bootout "gui/$(id -u)/com.wahbun.wheel.docker-watchdog"
```

再次启用使用上面的 bootstrap。故障测试应使用 mocks，不要为验收故意中断实盘 Gateway。


## Online backups and access-log rotation

`ops/maintenance.py` runs hourly through `com.wahbun.wheel.maintenance`.
It uses SQLite online backup for the order database and configured performance
history, validates integrity, and retains 14 UTC daily copies in the private
`~/Library/Application Support/Wheel/Maintenance` directory. These are same-disk
recovery copies, not protection against loss of the Mini or its disk.
Gunicorn access/error logs rotate at 20 MiB, retaining seven archives. A verified
Gunicorn master receives USR1 to reopen logs without restarting workers. Launchd
stdout/stderr and other application logs are not truncated by this task.
Status is recorded in status.json; sanitized failures in last_failure.json.
Only newer success timestamps indicate recovery from a recorded failure.
Install after pushing code and updating Mini:

```sh
.venv/bin/python ops/install_maintenance.py --project "$PWD"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.wahbun.wheel.maintenance.plist"
```

To restore, stop Wheel deliberately during a maintenance window, retain the live
DB and WAL files, and restore a selected verified copy. Never overwrite a live
order database; reconcile broker orders before enabling execution afterward.


## iOS account selector

Settings offers Demo, IB Paper and Live. Demo is local sample data. Paper/Live
select a private Mini profile. With the optional local Gateway login profiles
below, the backend recreates the existing Gateway service in the selected mode.
Live authentication still requires IB Key approval on your phone. The app waits
for account verification; switching never cancels orders or closes positions.

Provision `~/Library/Application Support/Wheel/account-profiles.json` (mode 600),
or set `WHEEL_ACCOUNT_PROFILES`, with `paper` and `live` objects containing complete
connection configurations. Paper uses port 4002 and its DU account; Live uses
port 4001 and its U account. Give each profile a separate absolute `db_path`.
Credentials do not belong in this file or Git. Preserve each profile's existing
read-only/execution permissions. The selected configuration is atomically saved
to `CONNECTION_CONFIG` (default `connection.json`) and survives restart.

The shared backend has one selected account for all clients. Switching closes
market subscriptions, rebuilds account services and rotates a write epoch.
Clients must obtain `account_epoch` from a verified portfolio response and attach
`X-Wheel-Account-Epoch` to writes. Stale or missing epochs are rejected, including
requests queued before a switch. Legacy web clients without this header remain
read-only when profiles are provisioned. The iOS app clears displayed account data
and cached chart packets while switching; unresolved local order submissions
block switching. Broker orders remain active at IB regardless of app mode.


### Optional automatic Gateway login

Create private (600) `live.json` and `paper.json` files under
`~/Library/Application Support/Wheel/gateway` (directory 700). Each contains the
existing Docker environment values `TWS_USERID`, `TWS_PASSWORD`, `TRADING_MODE`,
`VNC_SERVER_PASSWORD` and `READ_ONLY_API`; mode must match the file name. Preserve
existing API permissions. These files are local secrets and must never enter Git.
The controller passes them as process environment to `docker compose up -d
--no-deps --pull never ib-gateway`, suppresses command output and uses one bounded
job. It does not run a second Gateway or retry failed login jobs automatically.
Default compose directory is `~/Docker/ib-gateway`; override with
`WHEEL_GATEWAY_COMPOSE_DIR`. Optional path overrides: `WHEEL_GATEWAY_PROFILES` and
`WHEEL_DOCKER_CLI`. With no credential directory, manual Gateway login still works.
Demo hides connection controls without erasing the stored backend address.

The checked-in Gateway compose override selects `IB Key` automatically when IB
offers multiple authentication devices. Approval still happens on your phone.

### Preserve Gateway preferences during upgrades

All checked-in Gateway Compose paths explicitly set `AUTO_RESTART_TIME` to
`11:45 PM` and leave `AUTO_LOGOFF_TIME` empty. IBC reapplies automatic restart
at startup, including after image replacement. Time follows the Gateway time
zone (America/New_York in the dual and warm profiles), not the Pro clock.
This is daily automatic restart, not daily logoff. IB may still require weekly
or exceptional authentication; image upgrades can also require a fresh login.

Before an upgrade, privately back up the active settings directory and Compose
configuration. Retain the dual bind mount `/sessions` and its separate
`settings_live` / `settings_paper` directories. Never replace these with empty
folders or restore old authentication files into an active session. After the
upgrade, verify Lock and Exit in both sessions and the effective IBC
`AutoRestartTime`, as well as the existing API permissions. Do not restart a
running Gateway merely to apply this deployment preference.

### Dual Gateway window layout

Install `ops/com.wahbun.gateway-window-layout.plist` into the Mini user's
`~/Library/LaunchAgents/` and bootstrap it with launchctl. The job runs
`ops/gateway-window-layout.py` every 30 seconds while the user is logged in.
It uses Docker's existing socat/X11 socket, requiring no extra image packages.
Only when exactly two visible Gateway main windows exist does it place them
side by side. It records the container start, window IDs and screen size locally;
existing windows are not continually repositioned. New windows after a restart
or container replacement are automatically arranged. Login/configuration dialogs
are excluded. It never submits input or touches broker/API settings.
Disable with `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.wahbun.gateway-window-layout.plist`.


## Paper historical-data recovery

`ops/paper_gateway_watchdog.py` passively watches actual cold-history results;
it creates no extra market-data polling. Only a verified sole DU account on
4002 records evidence. At least three timeout-shaped results across two contracts,
spanning three minutes within ten minutes, with a failure in the last two minutes,
are required. Fast empty results, explicit IB errors, HTTP 503 alone and idle
markets do not trigger recovery. Fresh historical bars clear the failure evidence.

The local LaunchAgent checks every minute. It targets only the Java child of
`/tmp/pid_paper` inside `wheel-gateway-dual`, verifies the settings_paper path,
and uses IBC's COLDRESTART marker. Live and the Docker container stay running.
Uncertain local orders or unreadable order DB block recovery. No orders are
replayed. One attempt per outage remains latched until fresh history succeeds;
cooldown is 30 minutes and the rolling daily maximum is two attempts. Authentication
or an unconfirmed restart requires manual attention, not a restart loop.
This detects cold-history stalls, not every possible stale streaming condition.

Install on Mini after GitHub push/pull:
```
.venv/bin/python ops/install_paper_gateway_watchdog.py --project "$PWD"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.wahbun.wheel.paper-gateway-watchdog.plist"
```
State: `~/Library/Application Support/Wheel/PaperGatewayWatchdog/state.json`.
Logs: `logs/paper-gateway-watchdog.log`. No phone push notification is provided.
