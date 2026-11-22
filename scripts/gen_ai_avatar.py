"""生成 AI 浮窗用的本地头像占位图（避免依赖外网图片资源）"""
from PIL import Image, ImageDraw

SIZE = 512
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# 蓝色渐变底
for y in range(SIZE):
    t = y / SIZE
    r = int(14 + (29 - 14) * t)
    g = int(165 + (78 - 165) * t)
    b = int(233 + (216 - 233) * t)
    draw.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

# 圆形遮罩
mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).ellipse([0, 0, SIZE - 1, SIZE - 1], fill=255)
img.putalpha(mask)
draw = ImageDraw.Draw(img)

# 机器人脸
draw.rounded_rectangle([110, 140, 402, 400], radius=60, fill=(255, 255, 255, 235))
draw.ellipse([170, 215, 235, 280], fill=(30, 64, 175))
draw.ellipse([277, 215, 342, 280], fill=(30, 64, 175))
draw.arc([205, 290, 307, 360], start=10, end=170, fill=(30, 64, 175), width=14)
draw.rectangle([240, 98, 272, 150], fill=(255, 255, 255, 235))
draw.ellipse([222, 66, 290, 118], fill=(255, 255, 255, 235))

img.save(r"E:\eems\app01\static\img\ai_avatar.png")
print("OK")
