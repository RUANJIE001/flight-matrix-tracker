# ✈️ Flight Price Matrix Tracker (多平台机票价格弹性矩阵监控器)

一款基于 **GitHub Actions** 自动化定时运行的多平台机票监控工具。支持 **Google Flights**、**携程 (Trip.com)**、**天巡 (Skyscanner)** 三大平台，内置 **$\pm 1$ 天弹性日期矩阵（$3 \times 3 = 9$ 组组合）** 比价算法，并在降价或定时时自动推送精美 HTML 邮件与移动端通知。

---

## ✨ 核心特性

- 🌐 **多平台聚合比价**：同时横向对比 Google Flights、携程（Trip.com 海外接口）和天巡 Skyscanner。
- 📊 **$\pm 1$ 天弹性日期矩阵**：自动以出发日 $a$ 与返程日 $b$ 为中心，计算 $[a-1, a, a+1] \times [b-1, b, b+1]$ 共 9 组往返组合，找出最省钱的出行组合。
- ⚡ **极速与配额优化**：
  - 携程与天巡：采用轻量 REST API 直接交互，**零浏览器损耗**。
  - Google Flights：Playwright 无头模式开启强力**资源拦截**（静默阻断图片、媒体、字体等请求），单次运行仅需约 20 秒。
- 📬 **富文本 HTML 矩阵邮件**：自动生成 9 宫格价格热力表、标出达标最低价，并提供直达各平台的预订链接。
- ⏰ **云端 7x24 全自动运行**：基于 GitHub Actions Cron 调度，免费免开机，每次运行自动将 `history.json` 价格历史保存回仓库。

---

## 🚀 快速上手 (本地运行)

### 1. 克隆与安装依赖
```bash
git clone <your-repo-url>
cd flight-matrix-tracker

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 配置航线与邮箱
复制配置模板：
```bash
cp config.example.yaml config.yaml
```
编辑 `config.yaml`：
- 修改航线代码（如 `PVG` ⇄ `TYO`）与基准日期。
- 填写你的 SMTP 邮箱账号和授权码（如 QQ邮箱 / 163邮箱 / Gmail）。

### 3. 本地运行测试
```bash
python tracker.py
```

---

## ☁️ 部署到 GitHub Actions (零成本 7x24 云端监控)

### 步骤 1：将代码推送到你的 GitHub 仓库
在本地仓库根目录下执行：
```bash
git remote add origin https://github.com/<你的用户名>/flight-matrix-tracker.git
git branch -M main
git push -u origin main
```

### 步骤 2：配置 GitHub Secrets (Gmail 邮箱密码凭据)
进入你的 GitHub 仓库页面，点击 **Settings** -> **Secrets and variables** -> **Actions**，点击 **New repository secret** 添加：

| Secret 名称 | 示例值与说明 | 是否必填 |
| :--- | :--- | :--- |
| `EMAIL_SENDER` | 你的发件 Gmail 账号，如 `your_email@gmail.com` | **必填** |
| `EMAIL_AUTH_CODE` | Google 16 位**应用专用密码**（形如 `abcd efgh ijkl mnop`） | **必填** |
| `EMAIL_RECIPIENT` | 接收提醒的目标邮箱（可与发件人一致） | **必填** |
| `SMTP_SERVER` | 填 `smtp.gmail.com`（默认已内置，可不填） | 选填 |
| `SMTP_PORT` | 填 `587`（默认推荐 587 STARTTLS，可不填） | 选填 |

> 📌 **如何获取 Gmail 16 位应用专用密码 (App Password)？**
> 1. 打开 Google 账号安全设置：[myaccount.google.com/security](https://myaccount.google.com/security)
> 2. 确保已开启 **两步验证 (2-Step Verification)**。
> 3. 访问 [Google App Passwords (应用专用密码)](https://myaccount.google.com/apppasswords)。
> 4. 应用名称输入 `FlightMonitor`，点击创建。
> 5. 系统将生成一段 **16 位字母密码**（形如 `abcd efgh ijkl mnop`）。直接将其复制填入 `EMAIL_AUTH_CODE` 即可（**脚本内置清洗算法，会自动过滤掉内部空格**）。
> 6. 本脚本严格遵循云端 SMTP 规范：默认优先走 **`587` 端口 (STARTTLS)** 并自带 **`465` (SSL) 自动故障倒换**，在云端 Linux 执行机上极其稳定。

*(注：航线参数既可以在 `config.example.yaml` 里直接提交，也可以在 GitHub 的 Repository Variables 中设置 `ORIGIN`, `DEST`, `DEPART_DATE`, `TARGET_PRICE` 等进行灵活覆盖)*

### 步骤 3：赋予自动保存权限
在仓库 **Settings** -> **Actions** -> **General** -> **Workflow permissions** 中，选择 **Read and write permissions** 并保存（以便 Actions 自动保存 `history.json` 历史记录）。

### 步骤 4：测试与自动化执行
1. 点击仓库上方的 **Actions** 标签页。
2. 找到 **Flight Price Matrix Monitor** 工作流。
3. 点击右侧的 **Run workflow** 按钮即可手动立即触发一次比价并发送测试邮件！
4. 之后系统将按照 `.github/workflows/monitor.yml` 中配置的 Cron 周期（默认每 4 小时）在云端自动运行。

---

## 📂 项目结构

```
flight-matrix-tracker/
├── .github/workflows/
│   └── monitor.yml           # GitHub Actions 调度工作流
├── scrapers/
│   ├── base.py               # 统一航线数据规范与接口抽象
│   ├── google_flights.py     # Google Flights 快速并发抓取器
│   ├── ctrip_trip.py         # 携程 / Trip.com REST 接口适配器
│   └── skyscanner.py         # 天巡 Skyscanner 比价适配器
├── matrix.py                 # ±1天 9组笛卡尔积组合计算与矩阵分析器
├── notifier.py               # 响应式 HTML 矩阵邮件与 Webhook 发送器
├── tracker.py                # 监控主流程控制与本地持久化
├── config.example.yaml       # 基础配置文件模板
├── requirements.txt          # Python 依赖清单
└── history.json              # 自动生成的最近 500 次价格记录
```

---

## 📄 License
MIT License
