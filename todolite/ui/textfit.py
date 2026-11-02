"""Cắt chữ cho vừa chỗ. Logic thuần, hàm đo truyền từ ngoài vào nên test được mà không cần cửa sổ."""


def fit_text(measure, content, width):
    """Cắt chữ vừa bề rộng, thêm dấu ba chấm. Rộng tới mức không còn chữ nào thì trả về chuỗi rỗng."""
    if measure(content) <= width:
        return content
    low, high = 0, len(content)
    while low < high:
        middle = (low + high + 1) // 2
        if measure(content[:middle] + "…") <= width:
            low = middle
        else:
            high = middle - 1
    return content[:low].rstrip() + "…" if low else ""


def fit_parts(measure, content, width, separator):
    """Bỏ dần các ý cuối cho vừa bề rộng, chỉ còn một ý mà vẫn thừa thì mới cắt bằng dấu ba chấm."""
    if measure(content) > width:
        parts = content.split(separator)
        while len(parts) > 1:
            parts.pop()
            candidate = separator.join(parts)
            if measure(candidate) <= width:
                return candidate
        content = parts[0]
    return fit_text(measure, content, width)


def uniform_columns(total, want, count, gap):
    """Bề rộng count cột cùng nhóm uniform, cách nhau bởi khe gap không giãn, đúng như grid của Tk chia: mỗi cột bắt đầu từ
    bề rộng cần lớn nhất want, phần thừa hay thiếu chia theo trọng số cộng dồn, phép chia nguyên cắt về phía 0 như trong C."""
    sizes = [want if index % 2 == 0 else gap for index in range(2 * count - 1)]
    offsets, edge = [], 0
    for size in sizes:
        edge += size
        offsets.append(edge)
    diff, weight = total - edge, 0
    for index in range(len(sizes)):
        weight += index % 2 == 0
        part = diff * weight
        offsets[index] += part // count if part >= 0 else -(-part // count)
    return [offsets[index] - (offsets[index - 1] if index else 0) for index in range(0, len(sizes), 2)]


def side_by_side(room, text, extra):
    """Chia chỗ như pack: phần chữ giãn được lấy đủ bề rộng cần trước, phần đứng sau chỉ nhận chỗ còn lại, tối đa extra,
    chỗ thừa trả về phần chữ. Trả về (chữ, phần sau)."""
    after = max(0, min(extra, room - text))
    return room - after, after


def button_text_top(height, edge, line):
    """Đỉnh dòng chữ trong CTkButton cao height: lưới của Tk chia phần dư cho hàng trên, ô chữ, hàng dưới theo trọng số
    1000:1:1000 rồi làm tròn xuống, nhãn (cao line, viền 1) đứng giữa ô của nó, hai hàng lề tối thiểu edge."""
    spare = height - 2 * edge - line
    above = spare * 1000 // 2001
    return edge + above + (spare * 1001 // 2001 - above) // 2 + 1


def button_shape(asked, size, scale):
    """Cỡ hình CTkButton thực vẽ: cỡ lấy lại từ sự kiện Configure bằng phép chia rồi nhân số thực, hạ xuống số chẵn.
    Cỡ đã xin còn khớp sau khi làm tròn thì CustomTkinter giữ nguyên nó."""
    current = asked if all(round(a) == round(b / scale) for a, b in zip(asked, size)) else [b / scale for b in size]
    return [int(value * scale / 2) * 2 for value in current]
