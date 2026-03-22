from PIL import Image

# 替换为你实际的文件路径
with Image.open("1.gif") as img:
    # 获取第一帧的停留时间（毫秒）
    duration = img.info.get('duration', 100) 
    total_frames = getattr(img, "n_frames", 1)
    
    # 计算帧率 (1000毫秒 / 单帧时长)
    fps = 1000 / duration if duration > 0 else 0
    
    print(f"总帧数: {total_frames}")
    print(f"单帧时长: {duration} ms")
    print(f"实际帧率: 大约 {fps:.1f} FPS")