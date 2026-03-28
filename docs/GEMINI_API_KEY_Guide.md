# 获取 Google Gemini API Key 指南

## 1. 注册 Google 账号

如果你还没有 Google 账号，请先前往 [accounts.google.com](https://accounts.google.com) 注册。

## 2. 访问 Google AI Studio

打开浏览器，访问 **Google AI Studio**：

```
https://aistudio.google.com/
```

使用你的 Google 账号登录。

## 3. 生成 API Key

1. 登录后，点击左侧菜单中的 **「Get API key」**（获取 API 密钥）
2. 点击 **「Create API key」**（创建 API 密钥）
3. 在弹窗中选择一个已有的 Google Cloud 项目，或点击 **「Create API key in new project」** 创建新项目
4. 系统会自动生成一个 API Key，格式类似：`AIzaSy...`
5. **立即复制并保存此 Key**（页面关闭后无法再次查看完整 Key）

## 4. 配置到 DRT 系统

### 方式一：通过系统界面配置（推荐）

1. 登录 DRT 系统
2. 点击左侧菜单 **「Settings」**
3. 在 **AI Configuration** 区域，将 API Key 粘贴到输入框
4. 点击 **「Save」** 保存
5. 点击 **「Test Connection」** 验证 Key 是否有效

### 方式二：通过 .env 文件配置

在项目根目录 `ai_drt_system/` 下编辑 `.env` 文件：

```
GEMINI_API_KEY=你的API密钥
```

支持配置多个 Key（逗号分隔，系统会自动轮换以应对配额限制）：

```
GEMINI_API_KEY=Key1,Key2,Key3
```

保存后重启应用即可生效。

## 5. 免费额度说明

Google Gemini API 提供免费使用额度（Free Tier）：

| 模型 | 免费额度 |
|------|---------|
| Gemini 2.5 Flash | 每分钟 10 次请求 |
| Gemini 2.0 Flash | 每分钟 15 次请求 |
| Gemini 2.0 Flash Lite | 每分钟 30 次请求 |

DRT 系统会按 `gemini-2.5-flash` → `gemini-2.0-flash` → `gemini-2.0-flash-lite` 的顺序自动降级，确保在配额不足时仍能正常工作。

> **注意**：免费额度政策可能随时调整，请以 [Google AI Studio](https://aistudio.google.com/) 官网信息为准。

## 6. 常见问题

### Q: API Key 无效或测试连接失败？
- 确认 Key 复制完整，没有多余空格
- 确认你的网络可以访问 Google 服务
- 在 Google AI Studio 中检查 Key 是否已被禁用

### Q: 提示配额不足 (429 Quota Exceeded)？
- 系统会自动重试并降级到更低版本的模型
- 可以配置多个 API Key 进行轮换
- 等待 1 分钟后配额会自动恢复

### Q: 不配置 API Key 可以使用系统吗？
- 可以。系统核心功能（记录管理、导入导出、统计图表）不依赖 AI
- AI 诊断功能在无 API Key 时会降级为历史记录匹配和静态故障字典查询
