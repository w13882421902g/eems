"""
图片验证码工具（基于 Pillow 生成）

生成思路：
1. 在白色画布上随机写 5 个大写字母；
2. 叠加随机噪点、干扰弧线、干扰直线，机器识别难度更高；
3. 做一次边缘增强滤镜，让字符与背景更融合；
4. 返回 PIL 图片对象和验证码明文，由视图层负责存 session 和输出 PNG。

注意：字体路径写死为 Windows 的 arial.ttf，
如果换到 Linux 服务器部署，需要改成服务器上存在的字体文件。
"""
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def check_code(width=120, height=30, char_length=5,
               font_file="C:\\Windows\\Fonts\\arial.ttf", font_size=28):
    """生成验证码图片和验证码字符串"""
    code = []
    img = Image.new(mode='RGB', size=(width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img, mode='RGB')

    def rnd_char():
        # 随机大写字母：ASCII 65~90 对应 A~Z
        return chr(random.randint(65, 90))

    def rnd_color():
        # 随机颜色：蓝色分量起点偏低，避免生成纯白/浅色导致看不清
        return (random.randint(0, 255), random.randint(10, 255), random.randint(64, 255))

    # 写文字：每个字符的纵向位置随机偏移，增加识别难度
    font = ImageFont.truetype(font_file, font_size)
    for i in range(char_length):
        char = rnd_char()
        code.append(char)
        h = random.randint(0, 4)
        draw.text([i * width / char_length, h], char, font=font, fill=rnd_color())

    # 写干扰点
    for _ in range(40):
        draw.point([random.randint(0, width), random.randint(0, height)], fill=rnd_color())

    # 写干扰圆圈（用 90 度圆弧模拟小圈）
    for _ in range(40):
        draw.point([random.randint(0, width), random.randint(0, height)], fill=rnd_color())
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.arc((x, y, x + 4, y + 4), 0, 90, fill=rnd_color())

    # 画干扰线：连接两个随机点
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=rnd_color())

    # 边缘增强：让字符边界更明显，同时保留噪点干扰
    img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
    return img, ''.join(code)


def captcha_image_stream():
    """
    生成验证码图片字节流和验证码字符串。

    Django 的 HttpResponse 可以直接返回 bytes，
    所以把图片保存到内存中的 BytesIO，再 getvalue() 取字节，避免落盘临时文件。
    """
    img, code_str = check_code()
    stream = BytesIO()
    img.save(stream, 'png')
    return stream.getvalue(), code_str
