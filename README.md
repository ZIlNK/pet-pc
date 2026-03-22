# Desktop Pet 桌面宠物

一个可爱的桌面宠物应用，支持动画和休息提醒功能。

## 功能特性

- 🐾 可拖拽的桌面宠物
- 🎬 多种动画效果（行走、坐姿、阅读）
- ⏰ 定时休息提醒
- 🎯 惯性滑动和重力掉落效果
- ⚙️ 可扩展的动作配置系统
- 🎥 绿幕视频转透明GIF工具

## 安装

```bash
uv sync
```

开发工具依赖（可选）：

```bash
uv sync --group dev
```

## 运行

```bash
uv run desktop-pet
```

或者：

```bash
uv run python -m desktop_pet
```

## 项目结构

```
desktop_pet/
├── config/                  # 配置文件
│   ├── default_config.json  # 默认配置（勿修改）
│   └── user_config.json     # 用户配置（自定义修改）
├── src/desktop_pet/         # 源代码
│   ├── __init__.py
│   ├── __main__.py          # 入口点
│   ├── pet.py               # 主程序
│   ├── states.py            # 状态枚举
│   ├── utils.py             # 工具函数
│   └── config_manager.py    # 配置管理器
├── assets/                  # 资源文件
│   ├── images/              # 静态图片
│   └── animations/          # 动画GIF
├── scripts/                 # 辅助脚本
│   └── green_screen_to_gif.py  # 绿幕视频转GIF工具
└── tools/                   # Photoshop脚本
```

## 绿幕视频转GIF工具

将绿幕背景的MP4视频转换为透明背景的GIF动画。

### GUI版本（推荐）

提供可视化界面，支持实时预览和参数调整：

```bash
uv run python scripts/green_screen_to_gif_gui.py
```

**GUI功能：**
- 📺 实时预览原始画面和处理后效果
- 🎚️ 滑块调整绿幕容差和边缘柔和度
- 📐 自定义输出尺寸和帧率
- ▶️ 播放/停止预览动画
- 📋 自动生成动作配置JSON

### 命令行版本

```bash
uv run python scripts/green_screen_to_gif.py input.mp4 -o output.gif
```

### 常用参数

| 参数 | 说明 |
|------|------|
| `-o, --output` | 输出GIF文件路径 |
| `--fps` | 输出帧率（默认使用原视频帧率） |
| `--width` | 输出宽度 |
| `--height` | 输出高度 |
| `--tolerance` | 绿幕颜色容差（默认30） |
| `--softness` | 边缘柔和度（默认5） |
| `--no-loop` | 不生成循环播放 |

### 示例

```bash
# 指定输出尺寸
uv run python scripts/green_screen_to_gif.py input.mp4 -o output.gif --width 200 --height 159

# 调整绿幕容差（绿幕不干净时增加容差）
uv run python scripts/green_screen_to_gif.py input.mp4 -o output.gif --tolerance 40

# 指定帧率
uv run python scripts/green_screen_to_gif.py input.mp4 -o output.gif --fps 15

# 生成动作配置（方便添加到桌宠）
uv run python scripts/green_screen_to_gif.py input.mp4 -o assets/animations/wave/wave.gif --action-name wave --generate-config
```

### 添加新动作完整流程

1. 准备绿幕背景的MP4视频文件
2. 使用GUI工具或命令行工具转换为GIF：
   ```bash
   # GUI版本（推荐）
   uv run python scripts/green_screen_to_gif_gui.py
   
   # 或命令行版本
   uv run python scripts/green_screen_to_gif.py video.mp4 -o assets/animations/wave/wave.gif --width 200 --height 159 --generate-config --action-name wave --description "挥手动画"
   ```
3. 将输出的配置添加到 `config/user_config.json`
4. 运行桌宠查看效果

## 自定义配置

### 添加新动作

编辑 `config/user_config.json` 文件：

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
          "path": "animations/wave/wave_animation.gif",
          "width": 200,
          "height": 159
        }
      ]
    }
  }
}
```

### 禁用动作

```json
{
  "actions": {
    "sit": {
      "enabled": false
    }
  }
}
```

### 调整动作权重

权重越大，被选中的概率越高：

```json
{
  "actions": {
    "walk": {
      "weight": 2
    },
    "read": {
      "weight": 1
    }
  }
}
```

### 配置说明

| 字段 | 说明 |
|------|------|
| `enabled` | 是否启用该动作 |
| `weight` | 动作权重，数值越大被选中概率越高 |
| `type` | 动作类型：`animation`（动画）或 `movement`（移动） |
| `animations` | 动画文件列表，可添加多个 |
| `path` | 相对于 `assets` 目录的路径 |

## 依赖

### 运行依赖
- Python >= 3.10
- PyQt6
- Pillow

### 开发依赖（可选）
- opencv-python
- numpy
