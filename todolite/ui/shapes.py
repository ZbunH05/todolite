"""Hình chữ nhật bo góc khử răng cưa trên Canvas.

Đa giác của Tk không khử răng cưa nên góc bo bị gợn. Ở đây mỗi góc là một ảnh nhỏ đã tính độ phủ của
từng điểm ảnh rồi pha sẵn với màu nền, phần thân là hình chữ nhật thường. Ảnh được giữ lại theo màu
và bán kính, nên vẽ bao nhiêu hình cũng chỉ tốn vài ảnh, và vẽ lại nhanh như hình chữ nhật.
"""
import tkinter as tk
from math import hypot

SAMPLES = 4  # mỗi điểm ảnh lấy mẫu 4x4 lần

_corners = {}
_masks = {}
_serial = 0


def _channels(color):
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def _coverage(x, y, center, radius):
    """Tỉ lệ diện tích của điểm ảnh (x, y) nằm trong hình tròn."""
    if radius <= 0:
        return 0.0
    inside = sum(hypot(x + (column + 0.5) / SAMPLES - center, y + (row + 0.5) / SAMPLES - center) <= radius
                 for row in range(SAMPLES) for column in range(SAMPLES))
    return inside / SAMPLES ** 2


def _mask(radius, width):
    """Tỉ lệ nền, viền, ruột của từng điểm ảnh ở góc trên bên trái. Chỉ phụ thuộc hình dạng nên một lần tính dùng cho mọi màu."""
    key = (radius, width)
    mask = _masks.get(key)
    if mask is None:
        mask = []
        for y in range(radius):
            row = []
            for x in range(radius):
                outer = _coverage(x, y, radius, radius)
                inner = _coverage(x, y, radius, radius - width) if width else outer
                row.append((1 - outer, outer - inner, inner))
            mask.append(row)
        _masks[key] = mask
    return mask


def _pixel(weights, back, outline, fill):
    mixed = (sum(part * weight for part, weight in zip(channel, weights)) for channel in zip(back, outline, fill))
    return "#{:02x}{:02x}{:02x}".format(*(round(value) for value in mixed))


def corner_images(canvas, radius, fill, back, outline="", width=1):
    """Bốn ảnh góc theo thứ tự trên trái, trên phải, dưới trái, dưới phải."""
    key = (radius, fill, back, outline, width)
    images = _corners.get(key)
    if images is None:
        solid, behind = _channels(fill), _channels(back)
        ring = _channels(outline) if outline else behind
        rows = [[_pixel(weights, behind, ring, solid) for weights in row] for row in _mask(radius, width if outline else 0)]
        images = []
        for mirror_x, mirror_y in ((False, False), (True, False), (False, True), (True, True)):
            image = tk.PhotoImage(master=canvas, width=radius, height=radius)
            shaped = [row[::-1] if mirror_x else row for row in (rows[::-1] if mirror_y else rows)]
            image.put(" ".join("{" + " ".join(row) + "}" for row in shaped))
            images.append(image)
        _corners[key] = images
    return images


def frame(canvas, width, height, radius, inside, back, outline):
    """Viền thẻ vẽ đè lên nội dung của chính Canvas đó, để nội dung không lòi ra khỏi góc bo.

    inside là bốn màu ngay trong bốn góc, theo thứ tự như corner_images, back là màu phía ngoài thẻ.
    """
    edge = dict(outline="", fill=outline)
    canvas.create_rectangle(radius, 0, width - radius, 1, **edge)
    canvas.create_rectangle(radius, height - 1, width - radius, height, **edge)
    canvas.create_rectangle(0, radius, 1, height - radius, **edge)
    canvas.create_rectangle(width - 1, radius, width, height - radius, **edge)
    for index, color in enumerate(inside):
        x, y = (0, width - radius)[index % 2], (0, height - radius)[index // 2]
        canvas.create_image(x, y, image=corner_images(canvas, radius, color, back, outline)[index], anchor="nw")


def rounded(canvas, x0, y0, x1, y1, radius, fill, back, outline="", width=1, tags=()):
    """Vẽ hình bo góc trong khung [x0, x1) x [y0, y1). Trả về tag chung của mọi phần của hình.

    back là màu ngay phía sau hình. fill rỗng nghĩa là ruột trong suốt, tức cùng màu với back. Khi truyền tags
    thì không tạo tag riêng nữa, tag đầu tiên chính là tag chung: lịch tháng vẽ hàng trăm hình mỗi lần.
    """
    global _serial
    if tags:
        marks = tags
    else:
        _serial += 1
        marks = (f"shape{_serial}",)
    x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
    radius = max(min(round(radius), (x1 - x0) // 2, (y1 - y0) // 2), 0)
    if fill:
        # Ảnh góc không trong suốt nên thân chỉ cần một hình chữ nhật, các góc được ảnh phủ lên.
        canvas.create_rectangle(x0, y0, x1, y1, outline="", fill=outline or fill, tags=marks)
        if outline:
            canvas.create_rectangle(x0 + width, y0 + width, x1 - width, y1 - width, outline="", fill=fill, tags=marks)
    elif outline:
        edge = dict(outline="", fill=outline, tags=marks)
        canvas.create_rectangle(x0 + radius, y0, x1 - radius, y0 + width, **edge)
        canvas.create_rectangle(x0 + radius, y1 - width, x1 - radius, y1, **edge)
        canvas.create_rectangle(x0, y0 + radius, x0 + width, y1 - radius, **edge)
        canvas.create_rectangle(x1 - width, y0 + radius, x1, y1 - radius, **edge)
    if radius:
        images = corner_images(canvas, radius, fill or back, back, outline, width)
        for image, x, y in zip(images, (x0, x1 - radius, x0, x1 - radius), (y0, y0, y1 - radius, y1 - radius)):
            canvas.create_image(x, y, image=image, anchor="nw", tags=marks)
    return marks[0]
