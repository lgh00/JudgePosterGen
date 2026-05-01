import json
from PIL import Image, ImageDraw

# 读取 JSON 文件
with open('new_poster_layouts.json', 'r') as f:
    layouts = json.load(f)

# 颜色列表
colors = ['red', 'green', 'blue', 'yellow', 'purple', 'orange', 'cyan', 'magenta']

# 假设图片大小为 1000x1000
width, height = 1000, 1000

for i, layout in enumerate(layouts):
    for j, single_layout in enumerate(layout):
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        for k, rect in enumerate(single_layout):
            x1, y1, x2, y2 = rect
            color = colors[k % len(colors)]
            draw.rectangle([x1, y1, x2, y2], fill=color)
        img.save(f'layout_{i}_{j}.png')