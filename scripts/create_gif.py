from PIL import Image
import os
import re

# 图片目录路径
image_dir = r"c:/study/pet/sit/Exported_Group2_PNGs"
# 输出 GIF 路径
output_gif = r"c:/study/pet/sit/sit_animation.gif"

# 获取所有 PNG 图片文件
png_files = [f for f in os.listdir(image_dir) if f.endswith('.png')]

# 定义排序函数，提取文件名中的数字并排序
def sort_key(filename):
    # 提取文件名中的数字部分
    match = re.search(r'\d+', filename)
    if match:
        return int(match.group())
    return 0

# 按照数字顺序排序
png_files.sort(key=sort_key)

# 读取所有图片，并确保它们有透明通道
images = []
for file in png_files:
    file_path = os.path.join(image_dir, file)
    img = Image.open(file_path)
    # 确保图片有透明通道
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    images.append(img)

# 保存为 GIF，使用更可靠的方法确保透明背景
duration = 100  # 每张图片显示的毫秒数
loop = 0  # 0 表示无限循环

try:
    # 使用不同的方法处理透明背景
    # 1. 将每张图片转换为带透明通道的GIF帧
    gif_frames = []
    for img in images:
        # 创建一个新的图像，确保有透明通道
        gif_frame = Image.new('RGBA', img.size, (0, 0, 0, 0))
        gif_frame.paste(img, (0, 0), img)
        gif_frames.append(gif_frame)
    
    # 2. 保存GIF，使用正确的透明参数
    gif_frames[0].save(
        output_gif,
        format='GIF',
        append_images=gif_frames[1:],
        save_all=True,
        duration=duration,
        loop=loop,
        disposal=2,  # 2: 恢复到背景色（透明）
        optimize=False,  # 禁用优化以保持透明
        transparency=0,  # 设置透明色
        background=0,  # 设置背景色为透明色
        palette_mode='RGBA'  # 使用RGBA调色板
    )
    
    print(f"GIF 生成成功！输出路径: {output_gif}")
    print(f"共处理了 {len(images)} 张图片")
except Exception as e:
    print(f"生成 GIF 时出错: {e}")
    # 尝试另一种方法
    print("尝试使用替代方法生成GIF...")
    try:
        # 更简单的方法，直接保存，不做额外处理
        images[0].save(
            output_gif,
            format='GIF',
            append_images=images[1:],
            save_all=True,
            duration=duration,
            loop=loop,
            disposal=2,
            optimize=False
        )
        print(f"替代方法成功！GIF 输出路径: {output_gif}")
    except Exception as e2:
        print(f"替代方法也失败了: {e2}")
