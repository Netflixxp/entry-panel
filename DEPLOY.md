# Docker Compose 部署

## 1. 安装 Docker

Debian/Ubuntu 上先安装 Docker 和 Compose 插件：

```bash
apt update
apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 2. 部署面板

```bash
cd /opt
git clone <你的仓库地址> anytls-entry-panel
cd anytls-entry-panel
cp .env.example .env
mkdir -p data ssh
docker compose up -d --build
```

打开：

```text
http://服务器IP:8000
```

默认账号：

```text
admin / admin123
```

首次登录后请立刻改密码。

## 3. SSH 私钥

如果入口机用 SSH 私钥登录，把私钥放到项目的 `ssh/` 目录：

```bash
mkdir -p ssh
cp ~/.ssh/id_ed25519 ./ssh/id_ed25519
chmod 600 ./ssh/id_ed25519
```

面板里填写私钥路径：

```text
/ssh/id_ed25519
```

如果使用 SSH 密码登录，可以不挂私钥。

## 4. 更新

```bash
cd /opt/anytls-entry-panel
git pull
docker compose up -d --build
```

SQLite 数据在宿主机 `./data`，更新镜像不会丢数据。

## 5. 备份

```bash
cd /opt/anytls-entry-panel
tar czf anytls-entry-panel-backup.tar.gz data ssh .env
```

恢复时把 `data/`、`ssh/`、`.env` 放回项目目录，再执行：

```bash
docker compose up -d --build
```
