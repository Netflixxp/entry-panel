# AnyTLS SNI Entry Panel

一个轻量的中转入口管理面板，用 Python FastAPI 管理多台 Debian 入口机的 Nginx stream SNI 分流规则。

入口机只做四层转发：

- 客户端连接 `zhongzhuan.bbb.com:443`
- TLS ClientHello 中的 SNI 为 `edge-hk1.bbb.com`
- Nginx stream 使用 `ssl_preread` 读取 SNI
- 转发到落地 AnyTLS VPS，例如 `2.2.2.2:443`

入口机不解密 TLS，不保存 AnyTLS 密码，也不管理落地机 sing-box。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m app.main
```

默认访问：

- 地址：`http://127.0.0.1:8000`
- 用户名：`admin`
- 密码：`admin123`

首次登录后请立刻修改密码。

## Docker Compose

```bash
cp .env.example .env
mkdir -p data ssh
docker compose up -d --build
```

更多 VPS 部署和更新步骤见 [DEPLOY.md](./DEPLOY.md)。

## Linux systemd 示例

```ini
[Unit]
Description=AnyTLS SNI Entry Panel
After=network.target

[Service]
WorkingDirectory=/opt/entry-panel
ExecStart=/opt/entry-panel/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

## 入口机要求

- Debian 系统
- 可通过 SSH 登录
- 80/443 端口可被公网访问
- 默认网站域名已解析到入口机
- edge SNI 域名对应的证书和 AnyTLS 服务由落地机自行维护

## 安全提示

第一版为了调试方便，只实现单管理员密码登录。请不要直接暴露到公网，建议先放在 VPN、堡垒机或反向代理访问控制后面。
