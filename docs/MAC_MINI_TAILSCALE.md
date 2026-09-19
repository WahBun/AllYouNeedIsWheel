# Mac mini + Tailscale 部署

在 Mini 上运行一个网页版和 IB Gateway，MacBook、手机通过同一个 Tailnet
访问。下面使用占位符，不包含账户、设备 IP 或密码。

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

长期使用建议启用 HTTPS，前面的 IP/TCP 入口只用于初期验证或临时备用。
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
