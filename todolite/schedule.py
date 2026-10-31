"""Logic thời gian thuần: lặp lại, mốc nhắc, chữ hiển thị.

Không đụng database hay Windows, mọi hàm nhận `now` từ ngoài nên test được dễ dàng.
Thời gian lưu dạng chuỗi giờ địa phương 'YYYY-MM-DD HH:MM', so sánh chuỗi là so sánh thời gian.
"""
from collections import namedtuple
from datetime import date, datetime, time, timedelta

REMIND_CHOICES = (5, 15, 30, 60, 1440)
RECUR_LABELS = {"": "Không lặp", "daily": "Hằng ngày", "weekdays": "T2–T6", "weekly": "Hằng tuần", "monthly": "Hằng tháng"}
WEEKDAY_SHORT = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
WEEKDAY_LONG = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")
ALL_DAY_TIME = "23:59"

DEFAULT_EVENT_MINUTES = 30  # hạn chót có giờ hiện trên lịch tuần như một khối 30 phút

LATE_LIMIT = timedelta(hours=12)  # nhắc trễ hơn mức này (PC tắt lâu) thì bỏ, tóm tắt sáng sẽ nêu lại
STARTUP_LATE_LIMIT = timedelta(minutes=5)  # lúc khởi động đã có tóm tắt, không dội thêm nhắc cũ


def to_text(moment):
    return moment.isoformat(" ", "minutes")


def to_text_seconds(moment):
    return moment.isoformat(" ", "seconds")


def from_text(text):
    return datetime.fromisoformat(text)


def parse_offsets(text):
    """'30,15' -> [30, 15]"""
    return [int(part) for part in text.split(",") if part.strip().isdigit()]


def days_in_month(year, month):
    following = date(year + month // 12, month % 12 + 1, 1)
    return (following - timedelta(days=1)).day


def _month_step(due, months, anchor_day):
    index = due.year * 12 + due.month - 1 + months
    year, month = index // 12, index % 12 + 1
    return due.replace(year=year, month=month, day=min(anchor_day, days_in_month(year, month)))


def next_occurrence(due, rule, now):
    """Mốc kế tiếp của việc lặp lại, luôn sau cả `due` lẫn `now`.

    rule: daily | weekdays | weekly | monthly[:ngày gốc]. Giữ ngày gốc để việc "ngày 31"
    đi qua tháng 2 (28 ngày) rồi vẫn quay lại ngày 31 ở tháng sau.
    """
    kind, _, anchor = rule.partition(":")
    step = 0
    while True:
        step += 1
        if kind == "daily":
            candidate = due + timedelta(days=step)
        elif kind == "weekdays":
            candidate = due + timedelta(days=step)
            if candidate.weekday() > 4:
                continue
        elif kind == "weekly":
            candidate = due + timedelta(weeks=step)
        elif kind == "monthly":
            candidate = _month_step(due, step, int(anchor or due.day))
        else:
            raise ValueError(f"Luật lặp không hợp lệ: {rule}")
        if candidate > now:
            return candidate


def block_window(task):
    """(bắt đầu, kết thúc) của khối thời gian, hoặc None."""
    if not task["block_start"] or not task["block_minutes"]:
        return None
    start = from_text(task["block_start"])
    return start, start + timedelta(minutes=task["block_minutes"])


def active_block(tasks, now):
    """Khối đang chạy kết thúc sớm nhất: trả về (task, start, end) hoặc None."""
    best = None
    for task in tasks:
        window = block_window(task)
        if window and window[0] <= now < window[1] and (best is None or window[1] < best[2]):
            best = (task, window[0], window[1])
    return best


def next_block(tasks, now):
    """Khối sắp tới gần nhất: trả về (task, start, end) hoặc None."""
    best = None
    for task in tasks:
        window = block_window(task)
        if window and window[0] > now and (best is None or window[0] < best[1]):
            best = (task, window[0], window[1])
    return best


def task_events(task):
    """Mọi mốc thông báo của task: (thời điểm, loại, dấu mốc), sắp theo thời gian.

    `dấu mốc` là thời gian gốc: đổi deadline hoặc gia hạn khối thời gian thì dấu mốc
    đổi theo, nên nhắc được kích hoạt lại mà không cần xoá lịch sử đã gửi.
    """
    events = []
    due_at = task["due_at"]
    if due_at and not task["all_day"]:
        due = from_text(due_at)
        for minutes in parse_offsets(task["remind"]):
            events.append((due - timedelta(minutes=minutes), f"before:{minutes}", due_at))
        events.append((due, "due", due_at))
    window = block_window(task)
    if window:
        events.append((window[0], "block_start", task["block_start"]))
        events.append((window[1], "block_end", f"{task['block_start']}+{task['block_minutes']}"))
    if task["snooze_until"]:
        events.append((from_text(task["snooze_until"]), "snooze", task["snooze_until"]))
    events.sort(key=lambda item: item[0])
    return events


def collect(tasks, sent, now, late_limit=LATE_LIMIT):
    """Chia các mốc thành (cần hiện, cần bỏ qua, mốc tương lai gần nhất).

    PC ngủ dậy có thể làm nhiều mốc của một task cùng tới hạn: chỉ giữ mốc mới nhất
    để không dội thông báo, các mốc cũ vẫn được đánh dấu đã xử lý.
    """
    show, skip, upcoming = [], [], None
    for task in tasks:
        ready = []
        for fire_at, kind, stamp in task_events(task):
            if (task["id"], kind, stamp) in sent:
                continue
            if fire_at <= now:
                ready.append((fire_at, kind, stamp))
            elif upcoming is None or fire_at < upcoming:
                upcoming = fire_at
        if not ready:
            continue
        for fire_at, kind, stamp in ready[:-1]:
            skip.append((task, kind, stamp))
        fire_at, kind, stamp = ready[-1]
        (skip if now - fire_at > late_limit else show).append((task, kind, stamp))
    return show, skip, upcoming


def humanize(delta):
    """timedelta -> '1 giờ 20 phút'. Làm tròn lên để 14 phút 20 giây đọc là 15 phút."""
    minutes = max(int(delta.total_seconds() + 59) // 60, 0)
    if minutes < 60:
        return f"{minutes} phút"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} giờ {rest} phút" if rest else f"{hours} giờ"
    days, hours = divmod(hours, 24)
    return f"{days} ngày {hours} giờ" if hours else f"{days} ngày"


def countdown(delta):
    """timedelta -> '23:41' hoặc '1:02:05'."""
    seconds = max(int(delta.total_seconds()), 0)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def day_label(day, today):
    gap = (day - today).days
    if gap == 0:
        return "Hôm nay"
    if gap == 1:
        return "Ngày mai"
    if gap == -1:
        return "Hôm qua"
    if 1 < gap < 7:
        return WEEKDAY_SHORT[day.weekday()]
    return f"{day.day:02d}/{day.month:02d}" if day.year == today.year else f"{day.day:02d}/{day.month:02d}/{day.year}"


def when_label(due_at, all_day, now):
    """'Hôm nay 14:00', 'T6 09:30', '15/11' ..."""
    due = from_text(due_at)
    label = day_label(due.date(), now.date())
    return label if all_day else f"{label} {due:%H:%M}"


def _mid_sentence(label):
    """'Hôm nay 14:00' -> 'hôm nay 14:00', để đứng giữa câu."""
    return label[0].lower() + label[1:] if label.startswith(("Hôm", "Ngày")) else label


def _progress(task):
    return f" · Checkpoint {task['cp_done']}/{task['cp_total']}" if task["cp_total"] else ""


def describe_event(task, kind, now):
    """Nội dung thông báo tính theo thời gian thực, nên nhắc trễ vẫn nói đúng số phút còn lại."""
    title = task["title"]
    if kind in ("block_start", "block_end"):
        start, end = block_window(task)
        if kind == "block_end":
            return f"Hết giờ: {title}", "Đã xong hay cần thêm thời gian?" + _progress(task)
        return f"Bắt đầu: {title}", f"Khối {task['block_minutes']} phút, đến {end:%H:%M}" + _progress(task)
    if task["due_at"]:
        due = from_text(task["due_at"])
        label = _mid_sentence(when_label(task["due_at"], task["all_day"], now))
        if due <= now and not task["all_day"]:
            late = now - due
            head = "Đến hạn" if late < timedelta(minutes=2) else f"Quá hạn {humanize(late)}"
            return f"{head}: {title}", f"Hạn {label}" + _progress(task)
        if not task["all_day"]:
            return f"Còn {humanize(due - now)}: {title}", f"Hạn {label}" + _progress(task)
    return f"Nhắc lại: {title}", "Bạn đã hẹn nhắc lại việc này" + _progress(task)


def summary_message(overdue, today, now):
    """(tiêu đề, các dòng) cho thông báo tóm tắt đầu ngày."""
    parts = []
    if today:
        parts.append(f"{len(today)} việc hôm nay")
    if overdue:
        parts.append(f"{len(overdue)} quá hạn")
    if not parts:
        return "Hôm nay chưa có việc nào", ["Một ngày thoáng! Nhấn Ctrl+Alt+T để thêm việc nhanh."]
    picks = list(overdue[:2]) + list(today[:3])
    lines = []
    for task in picks[:3]:
        moment = "Quá hạn" if task in overdue else ("Cả ngày" if task["all_day"] else task["due_at"][11:16])
        lines.append(f"{moment} · {task['title']}")
    remaining = len(overdue) + len(today) - len(lines)
    if remaining > 0:
        lines[-1] += f"  (+{remaining} việc khác)"
    return " · ".join(parts), lines


# ---------- Lịch tuần và tháng ----------

CalendarItem = namedtuple("CalendarItem", "task start end all_day kind copy")  # copy: lần lặp tương lai, chưa có dòng riêng


def week_start(day):
    return day - timedelta(days=day.weekday())


def month_days(year, month):
    """Các ngày phủ kín lưới tháng, luôn bắt đầu từ thứ Hai: 28, 35 hoặc 42 ngày."""
    first = week_start(date(year, month, 1))
    last = week_start(date(year, month, days_in_month(year, month))) + timedelta(days=6)
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _occurrence(task, shift, copy):
    items = []
    window = block_window(task)
    if window:
        items.append(CalendarItem(task, window[0] + shift, window[1] + shift, False, "block", copy))
    if task["due_at"]:
        due = from_text(task["due_at"]) + shift
        if task["all_day"]:
            items.append(CalendarItem(task, due, due, True, "due", copy))
        elif not window or not window[0] + shift <= due <= window[1] + shift:
            items.append(CalendarItem(task, due, due + timedelta(minutes=DEFAULT_EVENT_MINUTES), False, "due", copy))
    return items


def calendar_items(tasks, first, last):
    """Mọi mục cần vẽ trong khoảng ngày [first, last), đã sắp theo thời gian.

    Việc lặp chỉ có một dòng cho lần kế tiếp, nên các lần sau được chiếu thêm (copy=True)
    để nhìn lịch tháng thấy đủ lịch tập, lịch họp định kỳ.
    """
    lower, upper = datetime.combine(first, time.min), datetime.combine(last, time.min)
    items = []
    for task in tasks:
        items.extend(_occurrence(task, timedelta(0), False))
        if task["recur"] and task["due_at"] and not task["done_at"]:
            base = from_text(task["due_at"])
            moment = next_occurrence(base, task["recur"], lower - timedelta(seconds=1))
            while moment < upper:
                items.extend(_occurrence(task, moment - base, True))
                moment = next_occurrence(moment, task["recur"], moment)
    items = [item for item in items if lower <= item.start < upper]
    items.sort(key=lambda item: (item.start.date(), not item.all_day, item.start, item.task["id"]))
    return items


def arrange_overlaps(items):
    """Xếp các mục trùng giờ thành cột song song: [(mục, cột, số cột trong cụm)]."""
    arranged, cluster, cluster_end = [], [], None

    def close_cluster():
        ends = []
        placed = []
        for item in cluster:
            for column, end in enumerate(ends):
                if end <= item.start:
                    ends[column] = item.end
                    break
            else:
                column = len(ends)
                ends.append(item.end)
            placed.append((item, column))
        arranged.extend((item, column, len(ends)) for item, column in placed)

    for item in sorted(items, key=lambda entry: (entry.start, entry.end)):
        if cluster and item.start >= cluster_end:
            close_cluster()
            cluster, cluster_end = [], None
        cluster.append(item)
        cluster_end = item.end if cluster_end is None else max(cluster_end, item.end)
    if cluster:
        close_cluster()
    return arranged
