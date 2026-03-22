#!/usr/bin/env python3
"""
GIF 转 APNG 命令行工具
提取 GIF 的每一帧和真实的延迟时间，无损转换为支持 Alpha 通道的 APNG 格式。
"""

import sys
import argparse
from pathlib import Path
from PIL import Image

def convert_gif_to_apng(input_path: str | Path, output_path: str | Path = None):
    input_path = Path(input_path)
    
    # 如果未指定输出路径，默认在同目录下生成同名的 .png 文件
    if not output_path:
        output_path = input_path.with_suffix('.png')
    else:
        output_path = Path(output_path)

    if not input_path.exists():
        print(f"❌ 错误: 找不到文件 {input_path}")
        return

    try:
        with Image.open(input_path) as gif:
            frames = []
            durations = []
            
            # 读取 GIF 循环次数 (0 表示无限循环)
            loop_count = gif.info.get('loop', 0)
            
            print(f"正在读取 GIF: {input_path.name}")
            print(f"总帧数: {gif.n_frames}")

            # 遍历提取每一帧
            for frame_idx in range(gif.n_frames):
                gif.seek(frame_idx)
                
                # 必须转换为 RGBA，确保透明通道正确解析
                frame_rgba = gif.convert("RGBA")
                frames.append(frame_rgba)
                
                # 获取当前帧的停留时间（毫秒），若没有获取到则默认 100ms (10 FPS)
                duration = gif.info.get('duration', 100)
                durations.append(duration)

            print(f"正在导出 APNG: {output_path.name} ...")
            
            # 导出为原生 APNG
            # disposal=2 极其重要：告诉渲染器在绘制下一帧前清空画布，防止半透明像素叠加产生“拖影”
            frames[0].save(
                output_path,
                format='PNG',
                save_all=True,
                append_images=frames[1:],
                duration=durations, # 传入列表以保留原本变帧率 GIF 的节奏
                loop=loop_count,
                disposal=2
            )
            
            print(f"✅ 转换成功! 文件已保存至: {output_path.absolute()}")
            
    except Exception as e:
        print(f"❌ 转换失败: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="无损 GIF 转 APNG 工具")
    parser.add_argument("input", help="要转换的 GIF 文件路径")
    parser.add_argument("-o", "--output", help="输出的 APNG (PNG) 文件路径 (可选)")
    
    args = parser.parse_args()
    convert_gif_to_apng(args.input, args.output)

if __name__ == "__main__":
    main()