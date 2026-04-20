# AI DRT System — Linux 服务器部署指南（SCP + SQLite）

## 前提

- 本地已有完整项目文件夹 `ai_drt_system/`
- 服务器为 Linux（Ubuntu/Debian/CentOS）
- 使用 SQLite 数据库（零配置，数据文件随项目走）

## 目录

1. [上传文件到服务器](#1-上传文件到服务器)
2. [一键部署](#2-一键部署)
3. [.env 配置说明](#3-env-配置说明)
4. [运维命令](#4-运维命令)
5. [Nginx 反向代理 + HTTPS（可选）](#5-nginx-反向代理--https可选)
6. [数据备份](#6-数据备份)
7. [常见问题](#7-常见问题)

---

## 1. 上传文件到服务器

```bash
# 本地执行 — 把项目文件夹传到服务器
scp -r ./ai_drt_system user@your-server:/opt/ai_drt_system
```

> 如果旧服务器有数据，确保 `drt_system.db` 一起传过去。

---

## 2. 一键部署

项目自带 `deploy.sh` 脚本，上传后在服务器执行即可：

```bash
ssh user@your-server
cd /opt/ai_drt_system
sed -i 's/\r$//' deploy.sh   # 修复 Windows 换行符
chmod +x deploy.sh
sudo ./deploy.sh
```

脚本会自动完成：
- 安装 Python 3、pip、venv
- 创建虚拟环境并安装依赖 + gunicorn
- 生成随机 `DRT_SECRET_KEY`（如 `.env` 中未设置）
- 创建 systemd 服务（`drt.service`）并启动
- 开放 5001 端口

部署完成后访问 `http://<服务器IP>:5001`。

---

## 3. .env 配置说明

`.env` 文件已预配好，部署前按需修改：

```ini
# App
FLASK_DEBUG=0                              # 生产环境保持 0
DRT_SECRET_KEY=CHANGE_ME_TO_RANDOM_STRING  # deploy.sh 会自动替换

# AI API Keys（至少配一个）
GEMINI_API_KEY=your_key                    # https://aistudio.google.com/apikey
GLM_API_KEY=your_key                       # https://open.bigmodel.cn

# 管理员账号（首次启动自动创建）
SEED_SUPERADMIN_USER=ismao
SEED_SUPERADMIN_PASS=your_password

# CORS
CORS_ORIGINS=https://drt.ismao.eu.cc
```

> 数据库使用 SQLite（零配置），数据文件为 `drt_system.db`，无需设置 `DATABASE_URL`。

---

## 4. 运维命令

```bash
# 查看状态
sudo systemctl status drt

# 查看日志
sudo journalctl -u drt -f

# 重启
sudo systemctl restart drt

# 停止
sudo systemctl stop drt

# 手动创建管理员
cd /opt/ai_drt_system
source .venv/bin/activate
flask create-admin --username admin --password your_password
```

---

## 5. Nginx 反向代理 + HTTPS（可选）

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

创建 `/etc/nginx/sites-available/drt`：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/drt /etc/nginx/sites-enabled/
sudo certbot --nginx -d your-domain.com
sudo systemctl reload nginx
```

---

## 6. 数据备份

```bash
# SQLite 备份 — 复制数据库文件即可
cp /opt/ai_drt_system/drt_system.db /backup/drt_system_$(date +%Y%m%d).db
```

---

## 7. 常见问题

| 问题 | 解决 |
|------|------|
| `ModuleNotFoundError` | `source .venv/bin/activate && pip install -r requirements.txt` |
| 端口 5001 被占用 | `sudo lsof -i :5001`，改 deploy.sh 中的 PORT 变量 |
| AI 分析无响应 | 检查 API Key 是否正确；大陆服务器访问 Gemini 需要代理 |
| 权限错误 | `sudo chown -R www-data:www-data /opt/ai_drt_system` |
