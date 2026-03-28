# AI DRT System 使用说明

## 系统简介

AI DRT (Defect Report Tracking) System 是一个基于 Web 的缺陷报告管理系统，专为制造产线的缺陷追踪和分析而设计。系统集成了 Google Gemini AI 智能诊断功能，可自动分析 Log 并生成 Root Cause 和 Action 建议。

---

## 1. 环境要求与启动

### 环境依赖

- Python 3.9+
- MySQL 数据库（或 SQLite 轻量模式）
- 浏览器（Chrome / Edge / Firefox）

### 安装依赖

```bash
cd ai_drt_system
pip install -r requirements.txt
```

### 配置数据库

编辑 `.env` 文件：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DRT_DB_TYPE` | sqlite | 数据库类型：`mysql` 或 `sqlite` |
| `DRT_MYSQL_HOST` | localhost | MySQL 主机 |
| `DRT_MYSQL_PORT` | 3306 | MySQL 端口 |
| `DRT_MYSQL_USER` | root | MySQL 用户名 |
| `DRT_MYSQL_PASSWORD` | root123 | MySQL 密码 |
| `DRT_MYSQL_DB` | ai_drt_system | 数据库名 |
| `GEMINI_API_KEY` | — | Gemini AI 密钥（参见 [GEMINI_API_KEY_Guide.md](GEMINI_API_KEY_Guide.md)） |

> 使用 SQLite 时无需安装 MySQL，数据库文件自动创建为 `drt_system.db`。

### 启动应用

```bash
python app.py
```

系统启动后访问：**http://localhost:5001**

### Windows 一键部署

使用部署脚本快速启动（后台运行 + 日志收集）：

```powershell
.\start_drt.ps1         # 后台启动，日志输出到 logs/ 目录
.\start_drt.ps1 -Stop   # 停止服务
.\start_drt.ps1 -Status # 查看运行状态
```

详见 [start_drt.ps1](../start_drt.ps1)。

### 默认登录账号

| 用户名 | 密码 | 角色 |
|-------|------|------|
| admin | admin123 | 管理员 |

> 首次启动时系统会自动创建此账号。也可通过 CLI 创建：`flask create-admin --username 用户名 --password 密码`

---

## 2. Dashboard（仪表盘）

登录后自动跳转到 Dashboard 页面，展示以下内容：

### KPI 卡片

- **Total Defects** — 总缺陷数
- **各 BU 缺陷数** — CRBU、WNBU、SRGBU、UABU、CSPBU 各自的缺陷总数
- **This Week** — 本周缺陷数

### 统计图表

| 图表 | 类型 | 说明 |
|------|------|------|
| Defect Class Distribution | 环形图 | 各缺陷类别的占比分布 |
| Weekly Trend | 折线图 | 按周（26WK01 格式）显示各 BU 的缺陷趋势 |
| Top 10 Stations | 横向柱状图 | 缺陷数最多的 10 个工站 |
| Top 10 Servers | 横向柱状图 | 缺陷数最多的 10 台服务器 |
| Top 10 PCAP/N | 横向柱状图 | 缺陷数最多的 10 个 PCAP/N |
| Top 10 Failures | 横向柱状图 | 出现次数最多的 10 种故障 |

### 筛选功能

页面顶部提供 BU、Date From、Date To 筛选器，支持按需过滤所有图表数据。

---

## 3. Defect Reports（缺陷记录管理）

### 3.1 记录列表

点击左侧菜单 **「Defect Reports」** 进入列表页。

**筛选条件**：BU、Defect Class、Defect Value、Station、日期范围、关键字搜索（支持 SN、Failure、PN 等字段模糊匹配）

**功能操作**：
- 点击表头可排序（支持升序/降序切换）
- 默认按 **Updated（更新时间）** 降序排列，最新修改的记录在最上面
- 24 小时内更新的记录以**浅绿色背景 + 绿色左边框**高亮显示
- 保存记录后自动跳转到列表页，对应行以**黄色闪烁**高亮标记
- 每页显示 10 / 25 / 50 / 100 条可选
- **New Record** — 新建记录
- **Export Excel** — 导出当前筛选结果为 Excel（支持 Include Log 选项）
- **Import** — 跳转到导入页面
- Apply / Reset 按钮均有视觉反馈动画

### 3.2 新建记录

点击 **「New Record」** 进入新建页面。

**必填字段**（标红星 *）：

| 字段 | 说明 |
|------|------|
| BU | 下拉选择：CRBU / WNBU / SRGBU / UABU / CSPBU |
| Week# | 自动计算（如 26WK13），可手动修改 |
| PCAP/N | UUT Type / PCAP 编号 |
| Station | 工站名称 |
| Server | 服务器名称 |
| SN | 产品序列号 |
| Failure | 故障描述 |
| Defect Class | 下拉选择（9 个选项） |
| Defect Value | 下拉选择（22 个选项） |

**可选字段**：Record Time、PN、Component SN、Root Cause、Action

**日志区域**：
- **Sequence Log** — 支持粘贴或拖拽上传 `.txt` / `.log` / `.gz` / `.gzm` 文件
- **Buffer Log** — 同上

### 3.3 AI 智能诊断

在新建/编辑页面，填写 Failure 和 Log 后，点击 **「Analyze Root Cause & Action with AI」** 按钮：

1. 系统将 Log 发送给 Gemini AI 进行分析
2. AI 返回 Root Cause 和 Action 建议
3. 可以点击 **「Accept Both」** 同时接受，或分别点击 **「Accept Root Cause Only」** / **「Accept Action Only」**

**AI 诊断四级降级机制**：

| 级别 | 方式 | 说明 |
|------|------|------|
| Tier 1 | Gemini AI | 调用 Google Gemini API 深度分析 |
| Tier 2 | 历史记录匹配 | 根据关键词搜索已有记录的 Root Cause |
| Tier 3 | 静态故障字典 | 内置的故障码对照表 |
| Tier 4 | 无建议 | 无法匹配时提示手动填写 |

### 3.4 AI Beautification（Root Cause & Action 润色）

在编辑页面，填写 Root Cause 和 Action 后，点击 **「Beautify with AI」** 按钮：

1. AI 对文本进行语法和清晰度优化，保持原始技术含义不变
2. 以 **Before / After 四格对比** 展示原文和润色后的结果
3. 可选择 **Accept Both** / **Accept Root Cause Only** / **Accept Action Only** / **Discard**
4. 只有确认后才会填写到表单中，不会自动覆盖

### 3.5 Log 管理

**Sequence Log / Buffer Log**：
- 支持粘贴或拖拽上传 `.txt` / `.log` / `.gz` / `.gzm` 文件
- 编辑时自动加载已有的 Log 数据（如 `log_content` 有数据会自动填入 Sequence Log）
- 每个 Log 区域有 **Clear** 按钮，带确认弹窗，可清除内容后重新上传

### 3.6 Same History Query（历史查询）

点击 **「Search」** 按钮，系统会根据 BU + Failure 精确匹配历史记录，返回最近 3 条已填写 Root Cause 的记录供参考。

### 3.5 记录详情

在列表中点击 **「View」** 查看完整详情，包括：
- 所有字段信息
- LOG 内容（支持点击 **「View Full Log」** 全屏查看）
- 编辑 / 删除操作

---

## 4. Import（数据导入）

点击左侧菜单 **「Import」** 进入导入页面，支持两种导入方式：

### 4.1 Excel 标准导入

**适用场景**：导入已整理好的完整缺陷记录

1. 先点击 **「Download Template」** 下载模板文件
2. 按模板格式填写数据
3. 选择 BU
4. 上传文件（`.xlsx` 格式）
5. 导入的记录直接进入缺陷列表（状态为 `complete`）

**自动处理**：
- 根据 Record Time 自动计算 Week#（格式：26WK01）
- 自动去重（SN + Record Time 相同即判定为重复）

### 4.2 Cesium 原始数据导入

**适用场景**：导入测试系统 Cesium 的原始数据

1. 选择 BU
2. 上传 Cesium 导出的 Excel 文件
3. 导入的记录进入 **Pending（待处理）** 状态

**自动映射字段**：

| Cesium 列名 | 系统字段 |
|-------------|---------|
| Record Time (UTC) | record_time |
| Serial Number | SN |
| Failing Test Name | Failure |
| Machine | Server |
| UUT Type | PCAP/N |
| Test Area | Station |

> Week# 根据 Record Time 自动计算。

**双模式解析**：系统优先使用 openpyxl 解析 Excel，如果遇到样式兼容问题（如 Cesium 导出的非标准 OOXML），自动回退到 zipfile+XML 原始解析模式，确保导入成功。

**Cesium 导入后续流程**：
1. 进入 **「Pending」** 页面查看待处理记录
2. 点击 **「Edit」** 补充必填字段（Defect Class、Defect Value 等）
3. 保存后记录自动从 Pending 转为正式记录

---

## 5. Pending（待处理记录）

点击左侧菜单 **「Pending」** 查看通过 Cesium 导入的草稿记录。

**功能**：
- **Uploaded 列** — 显示每条记录的上传时间
- **BU 筛选** — 按事业部过滤记录
- **Refresh** — 刷新列表（带旋转动画视觉反馈）
- **Edit** — 编辑记录，补充必填字段后保存即可转为正式记录
- **Delete** — 删除单条草稿
- **Batch Delete** — 批量删除选中的草稿

---

## 6. Export（数据导出）

在 Defect Reports 列表页点击 **「Export Excel」** 按钮：

- 导出当前筛选条件下的所有记录
- 生成符合 OOXML 规范的 `.xlsx` 文件（冻结表头、自适应列宽、带样式）
- **Include Log** 选项（默认勾选）：勾选时导出 LOG、Sequence Log、Buffer Log 三列
- 导出字段：BU, Week#, PCAP/N, Station, Server, SN, Record Time, Failure, Defect Class, Defect Value, Root Cause, Action, PN, Component SN
- UPDATED 字段不参与导出

---

## 7. Settings（系统设置）

点击左侧菜单 **「Settings」** 进入设置页面。

### AI Configuration

- 查看当前 API Key 状态（显示脱敏后的 Key）
- 更新 Gemini API Key
- 测试 API 连接是否正常

---

## 8. 字段说明速查

### Defect Class（9 类）

| 值 | 说明 |
|---|------|
| CND | Could Not Duplicate |
| Equipment | 设备问题 |
| Hardware | 硬件故障 |
| NPF | No Problem Found |
| OPERATOR_PROCESS | 操作/流程问题 |
| ORDER | 订单问题 |
| R&R | 返修 |
| TBD | 待确认 |
| TEST | 测试问题 |

### BU（5 个事业部）

CRBU、WNBU、SRGBU、UABU、CSPBU

### Week# 格式

`年份后两位` + `WK` + `周数`，例如：
- 2026 年第 1 周 → **26WK01**
- 2025 年第 52 周 → **25WK52**

---

## 9. 快捷键与技巧

- **筛选快捷操作**：修改筛选条件后点击 **Apply** 或按 **Enter** 即可刷新
- **Reset** 按钮可一键清除所有筛选条件
- **Log 拖拽上传**：直接将 `.txt` / `.log` / `.gz` 文件拖拽到 Log 输入区域即可自动读取
- **AI 诊断关键词**：在 AI 诊断时可输入额外关键词引导 AI 分析方向
