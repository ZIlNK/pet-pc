<div align="center">

# 🐱 Desktop Pet

**一个可爱、可扩展的桌面宠物应用**

让萌宠陪伴你的每一天，支持自定义动画、休息提醒、HTTP API 远程控制

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.0+-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/yourusername/desktop-pet)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [API 文档](#-http-api-远程控制) • [自定义](#-自定义配置) • [贡献指南](#-贡献指南)

</div>

---

## 📸 预览

<!-- 添加截图占位符 -->
```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│    🖼️ 在此处添加应用截图或 GIF 演示                       │
│                                                         │
│    建议尺寸: 800x400 或类似宽高比                         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## ✨ 功能特性

### 🎭 核心功能

| 功能 | 描述 |
|------|------|
| 🐾 **可拖拽宠物** | 用鼠标拖动宠物在屏幕上移动，支持惯性滑动和重力掉落 |
| 🎬 **丰富动画** | 支持行走、坐姿、阅读、睡觉等多种动画效果 |
| ⏰ **休息提醒** | 可配置的定时提醒功能，保护你的眼睛和健康 |
| 🎮 **运动模式** | 通过 GUI 控制面板或 API 精确控制宠物移动 |

### 🔧 高级功能

| 功能 | 描述 |
|------|------|
| 🌐 **HTTP API** | RESTful API 支持远程控制，可与第三方应用集成 |
| 📦 **资源包系统** | 支持加载不同的宠物资源包，轻松切换外观 |
| 🎥 **绿幕转换工具** | 内置工具将绿幕视频转换为透明 GIF，方便制作动画 |
| 👆 **点击检测** | 配置点击区域触发特定动画，增加交互性 |

### 🎯 技术亮点

- **信号槽架构** - PyQt 信号机制实现组件解耦
- **异步 API 服务器** - 基于 aiohttp 的高性能 HTTP 服务
- **配置热合并** - 用户配置与默认配置深度合并，灵活定制
- **状态机管理** - 清晰的状态流转保证行为一致性

---

## 🚀 快速开始

### 环境要求

- Python 3.10 或更高版本
- Windows / Linux / macOS

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/yourusername/desktop-pet.git
   cd desktop-pet
   ```

2. **安装依赖**

   使用 [uv](https://docs.astral.sh/uv/)（推荐）：
   ```bash
   uv sync
   ```

   或使用 pip：
   ```bash
   pip install -e .
   ```

3. **运行应用**
   ```bash
   uv run desktop-pet
   ```

   或：
   ```bash
   python -m desktop_pet
   ```

### 开发依赖

如需使用绿幕视频转换工具，安装开发依赖：

```bash
uv sync --group dev
```

### 打包为可执行文件

将应用打包成独立的 EXE 文件，方便分发：

```bash
# 安装开发依赖（包含 PyInstaller）
uv sync --group dev

# 打包成单个 EXE 文件
uv run python scripts/build.py

# 打包成目录形式（启动更快）
uv run python scripts/build.py --dir

# 极致体积优化
uv run python scripts/build.py --small
```

打包完成后，可执行文件位于 `dist/DesktopPet.exe`。

> **注意**：由于 PyQt6 框架较大，打包后的文件约 800MB。如需更小的体积，可考虑使用 `--dir` 模式配合压缩软件分发。

---

## 🌐 HTTP API 远程控制

Desktop Pet 提供完整的 HTTP API，支持远程控制宠物行为。

### 启动 API 服务器

右键点击宠物 → **运动模式** → **启动 API 服务器**

默认端口：`8080`

### API 端点

| 方法 | 端点 | 描述 | 请求体 |
|------|------|------|--------|
| `GET` | `/api/status` | 获取宠物状态（位置、模式、动画列表） | - |
| `POST` | `/api/mode` | 切换模式 | `{"mode": "motion"}` |
| `POST` | `/api/move` | 移动到指定坐标 | `{"x": 100, "y": 200}` |
| `POST` | `/api/move_by` | 相对移动 | `{"dx": 50, "dy": 0}` |
| `POST` | `/api/move_edge` | 移动到屏幕边缘 | `{"edge": "left"}` |
| `POST` | `/api/animation` | 播放动画（支持回调） | `{"name": "sit"}` |
| `POST` | `/api/walk` | 播放行走动画 | `{"direction": "left"}` |
| `GET` | `/api/animations` | 获取可用动画列表 | - |

### 快速示例

```bash
# 获取状态
curl http://localhost:8080/api/status

# 移动宠物
curl -X POST http://localhost:8080/api/move \
  -H "Content-Type: application/json" \
  -d '{"x": 500, "y": 300}'

# 播放动画
curl -X POST http://localhost:8080/api/animation \
  -H "Content-Type: application/json" \
  -d '{"name": "sit"}'
```

### 公网访问

使用 [ngrok](https://ngrok.com) 实现公网访问：

```bash
# 安装 ngrok
winget install ngrok.ngrok

# 配置 authtoken
ngrok config add-authtoken <your-token>

# 启动穿透
ngrok http 8080
```

> ⚠️ 公网访问时请配置适当的安全策略，详见 [API 安全配置](#安全配置)。

---

## 🎨 自定义配置

### 配置文件结构

```
config/
├── default_config.json  # 默认配置（请勿修改）
└── user_config.json     # 用户配置（覆盖默认值）
```

### 添加新动画

编辑 `config/user_config.json`：

```json
{
  "actions": {
    "wave": {
      "enabled": true,
      "weight": 1,
      "type": "animation",
      "description": "挥手动画",
      "animations": [
        {
          "path": "animations/wave/wave.gif",
          "width": 200,
          "height": 159
        }
      ]
    }
  }
}
```

### 配置说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用该动作 |
| `weight` | int | 动作权重（数值越大，触发概率越高） |
| `type` | string | `animation`（动画）或 `movement`（移动） |
| `animations` | array | 动画文件列表 |

### 安全配置

API 服务器支持 IP 白名单：

```json
{
  "api": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8080,
    "allowed_ips": ["127.0.0.1", "::1", "192.168.1.100"]
  }
}
```

使用内网穿透时，设置空数组允许所有访问：

```json
{
  "api": {
    "allowed_ips": []
  }
}
```

---

## 🛠️ 动画制作工具

内置绿幕视频转换工具，方便制作自定义动画。

### GUI 版本（推荐）

```bash
uv run python scripts/green_screen_to_gif_gui.py
```

**功能特性：**
- 实时预览原始画面和处理效果
- 滑块调整绿幕容差和边缘柔和度
- 自定义输出尺寸和帧率
- 自动生成配置 JSON

### 命令行版本

```bash
uv run python scripts/green_screen_to_gif.py input.mp4 -o output.gif \
  --width 200 --height 159 --fps 15
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o, --output` | 输出文件路径 | 必填 |
| `--fps` | 输出帧率 | 原视频帧率 |
| `--width` | 输出宽度 | - |
| `--height` | 输出高度 | - |
| `--tolerance` | 绿幕颜色容差 | 30 |
| `--softness` | 边缘柔和度 | 5 |

---

## 📁 项目结构

```
desktop_pet/
├── src/desktop_pet/         # 源代码
│   ├── pet.py               # 主程序入口
│   ├── api_server.py        # HTTP API 服务器
│   ├── motion_controller.py # 运动模式控制器
│   ├── config_manager.py    # 配置管理器
│   ├── pet_loader.py        # 资源包加载器
│   └── ...
├── config/                  # 配置文件
│   ├── default_config.json  # 默认配置
│   └── user_config.json     # 用户配置
├── pets/                    # 宠物资源包
│   └── default/             # 默认资源包
│       ├── meta.json        # 资源包元信息
│       ├── config/          # 资源包配置
│       └── animations/      # 动画文件
├── scripts/                 # 辅助脚本
│   ├── green_screen_to_gif.py      # CLI 转换工具
│   └── green_screen_to_gif_gui.py  # GUI 转换工具
└── README.md
```

---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/yourusername/desktop-pet.git
cd desktop-pet

# 安装开发依赖
uv sync --group dev

# 运行测试
uv run pytest
```

### 提交代码

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'feat: add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

### 代码规范

- 遵循 PEP 8 编码规范
- 添加必要的类型注解
- 为新功能编写测试

---

## 📋 路线图

- [ ] 支持 API Key 认证
- [ ] 添加 WebSocket 实时通信
- [ ] 支持更多动画格式（Lottie、APNG）
- [ ] 多显示器支持优化
- [ ] 国际化支持（i18n）
- [ ] 系统托盘集成
- [ ] 自动更新功能

---

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

---

## 🙏 致谢

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - 强大的 GUI 框架
- [aiohttp](https://docs.aiohttp.org/) - 异步 HTTP 服务器
- [Pillow](https://python-pillow.org/) - 图像处理库

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐️ Star！**

Made with ❤️ by [Your Name]

</div>