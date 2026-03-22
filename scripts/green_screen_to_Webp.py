#!/usr/bin/env python3
"""
绿幕视频转动态 WebP 工具
支持绿幕精准抠像、边缘柔化防锯齿、自定义输出帧率。
完美适配 PyQt6 的 QMovie 播放。
"""

import cv2
import numpy as np
from PIL import Image
from pathlib import Path
import argparse

def convert_video_to_webp(input_path: str, output_path: str = None, target_fps: int = 30):
    input_path = Path(input_path)
    
    if not output_path:
        output_path = input_path.with_suffix('.webp')
    else:
        output_path = Path(output_path)

    if not input_path.exists():
        print(f"❌ 错误: 找不到视频文件 {input_path}")
        return

    print(f"🎬 正在打开视频: {input_path.name}")
    cap = cv2.VideoCapture(str(input_path))
    
    # 获取原视频信息
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"   原视频帧率: {source_fps:.2f} FPS, 总帧数: {total_frames}")
    
    # 如果用户没有指定帧率，或者指定的帧率不合理，则使用原视频帧率
    fps = target_fps if target_fps > 0 else source_fps
    duration_ms = int(1000 / fps)
    print(f"   目标输出帧率: {fps} FPS (单帧时长: {duration_ms} ms)")

    frames = []
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_count += 1
        print(f"\r处理进度: {frame_count}/{total_frames}", end="")

        # 1. 转换颜色空间：BGR 转 HSV (HSV 更容易提取纯色绿幕)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # 2. 定义绿色的范围 (这个范围适用于绝大多数标准绿幕)
        # 如果你的视频绿幕偏暗或偏亮，可以微调这里的数值
        lower_green = np.array([35, 40, 40])
        upper_green = np.array([85, 255, 255])
        
        # 3. 创建绿幕遮罩 (绿色的地方为 255，其他地方为 0)
        mask = cv2.inRange(hsv, lower_green, upper_green)
        
        # 4. 反转遮罩：我们要保留的是非绿色的部分 (雷泽)
        mask_inv = cv2.bitwise_not(mask)
        
        # 5. 边缘柔化：轻微模糊遮罩，让人物边缘产生半透明过渡，彻底消除“狗牙”和“绿边”
        mask_inv = cv2.GaussianBlur(mask_inv, (3, 3), 0)
        
        # 6. 将原始画面 (BGR) 转换为带透明通道的画面 (BGRA)
        bgra = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
        
        # 7. 将我们做好的半透明遮罩赋值给 Alpha 通道
        bgra[:, :, 3] = mask_inv
        
        # 8. 将 OpenCV 的 BGRA 转换为 Pillow 需要的 RGBA
        rgba = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA)
        pil_img = Image.fromarray(rgba)
        
        frames.append(pil_img)

    cap.release()
    print("\n📦 视频处理完毕，正在编码为动态 WebP (可能需要几秒到十几秒)...")
    
    if frames:
        try:
            # 导出动态 WebP
            frames[0].save(
                output_path,
                format='WebP',
                save_all=True,
                append_images=frames[1:],
                duration=duration_ms, # 精确的单帧毫秒数
                loop=0,               # 0 表示无限循环播放
                lossless=False,       # 设为 False 允许适度压缩，防止文件过大
                quality=90,           # 画质 (0-100)，90 是画质和体积的绝佳平衡
                method=4              # 压缩寻优等级 (0-6)，4 是默认的性能/体积平衡点
            )
            print(f"✅ 转换成功! 完美 WebP 已保存至: {output_path.absolute()}")
        except Exception as e:
            print(f"❌ 导出失败: {str(e)}")
    else:
        print("❌ 未能提取到任何视频帧。")

def main():
    parser = argparse.ArgumentParser(description="绿幕视频转动态 WebP 工具 (PyQt6 完美适配)")
    parser.add_argument("input", help="要转换的绿幕视频文件路径 (例如 .mp4)")
    parser.add_argument("-o", "--output", help="输出的 WebP 文件路径 (可选)")
    parser.add_argument("-f", "--fps", type=int, default=30, help="输出帧率 (默认 30，决定了动图的播放速度)")
    
    args = parser.parse_args()
    convert_video_to_webp(args.input, args.output, args.fps)

if __name__ == "__main__":
    main()