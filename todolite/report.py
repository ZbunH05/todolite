"""Tờ tấu theo lệnh nhắn cho bot: /rp tình hình hôm nay tới lúc này, /today hạn định hôm nay, /week hạn định 7 ngày tới.

Cùng giọng với tờ tấu mỗi ngày (telegram.py) nhưng chỉ đọc database, nên chạy ngay trong tiến trình đọc tin
`--telegram-inbox` mà không phải nạp phần lịch vạn niên. Các hàm viết chữ dùng chung với tờ tấu mỗi ngày nằm ở đây.
Mọi con số tính theo lúc trả lời, nên /rp nhắn lúc nào cũng đúng tình hình lúc đó.
"""
import html
from datetime import timedelta

from .schedule import WEEKDAY_LONG, WEEKDAY_SHORT, active_block, from_text, humanize, when_label

MESSAGE_LIMIT = 4096  # Telegram đếm theo đơn vị UTF-16, mỗi emoji chiếm 2
MAX_LATE_ITEMS = 5
MAX_LIST_ITEMS = 8
TITLE_LENGTHS = (80, 48, 28)  # tin quá dài thì cắt tên việc ngắn dần, rồi mới tới bỏ dòng
ROUTINE_RULES = ("daily", "weekdays")
WEEK_DAYS = 7
SIGN_OFF = "Thần kính tấu!"


def _mid_sentence(title):
    """Viết thường chữ đầu để đặt giữa câu, trừ từ viết tắt như 'API' và tên riêng như 'Hà Nội'."""
    words = title.split()
    if title[1:2].isupper() or (len(words) > 1 and words[1][0].isupper()):
        return title
    return title[0].lower() + title[1:]


def _title(task, limit):
    title = task["title"]
    return title if len(title) <= limit else title[:limit - 1].rstrip() + "…"


def _name(task, limit):
    return html.escape(_title(task, limit), quote=False)


def _moment(task):
    return "" if task["all_day"] else f" lúc {task['due_at'][11:16]}"


def _bullets(lines, limit=MAX_LIST_ITEMS):
    shown = [f"• {line}" for line in lines[:limit]]
    if len(lines) > limit:
        shown.append(f"• và {len(lines) - limit} việc khác")
    return shown


def _is_routine(task):
    return task["recur"].split(":")[0] in ROUTINE_RULES


def _upcoming_line(task, today, limit):
    day = from_text(task["due_at"]).date()
    left = (day - today).days
    label = "Ngày mai" if left == 1 else f"{WEEKDAY_SHORT[day.weekday()]} {day:%d/%m}"
    return f"{label}{_moment(task)}{f', còn {left} ngày' if left > 1 else ''}: {_name(task, limit)}"


def _late_line(task, now, limit):
    late = now - from_text(task["due_at"])
    return f"{_name(task, limit)} (trễ {f'{late.days} ngày' if late.days else humanize(late)})"


def _block_line(row, limit):
    start = from_text(row["block_start"])
    return f"{start:%H:%M}–{start + timedelta(minutes=row['block_minutes']):%H:%M} {_name(row, limit)}"


def _length(text):
    return len(text.encode("utf-16-le")) // 2


def _within_limit(text):
    """Chốt an toàn cho độ dài: mỗi dòng là HTML trọn vẹn nên bỏ bớt dòng cuối không làm hỏng thẻ."""
    lines = text.split("\n")
    while _length("\n".join(lines)) > MESSAGE_LIMIT:
        lines.pop()
    return "\n".join(lines)


def _fitted(build):
    """build(độ dài tên việc) trả về các dòng của tin; tên ngắn dần tới khi tin vừa giới hạn của Telegram."""
    for limit in TITLE_LENGTHS:
        text = "\n".join(build(limit))
        if _length(text) <= MESSAGE_LIMIT:
            return text
    return _within_limit(text)


def _split_routine(tasks):
    return [task for task in tasks if not _is_routine(task)], [task for task in tasks if _is_routine(task)]


def _due_line(task, now, limit):
    """'<b>Họp nhóm</b> lúc 15:00 (còn 55 phút)', việc cả ngày thì '<b>Viết báo cáo</b> (cả ngày)'."""
    if task["all_day"]:
        return f"<b>{_name(task, limit)}</b> (cả ngày)"
    return f"<b>{_name(task, limit)}</b>{_moment(task)} (còn {humanize(from_text(task['due_at']) - now)})"


def _names(tasks, limit):
    names = ", ".join(_mid_sentence(_name(task, limit)) for task in tasks[:MAX_LIST_ITEMS])
    return names + (f" và {len(tasks) - MAX_LIST_ITEMS} việc khác" if len(tasks) > MAX_LIST_ITEMS else "")


def _day_title(day, today):
    name = f"{WEEKDAY_LONG[day.weekday()]} {day:%d/%m}"
    relative = {0: "Hôm nay", 1: "Ngày mai"}.get((day - today).days)
    return f"{relative}, {name}" if relative else name


def _late_section(late, now, limit):
    if not late:
        return []
    return [f"Đã trễ ({len(late)} việc):", *_bullets([_late_line(task, now, limit) for task in late], MAX_LATE_ITEMS)]


def today(store, now):
    """/today: việc trễ, việc còn hạn hôm nay, khối giờ, việc thường nhật và những gì đã xong."""
    overdue, current = store.summary_tasks(now)
    (late, routine_late), (due, routine_due) = _split_routine(overdue), _split_routine(current)
    routine, done, blocks, day = routine_late + routine_due, store.list_tasks("done_today", now), store.blocks_today(now), now.date()

    def build(limit):
        lines = [f"<b>Tâu Bệ hạ, hạn định hôm nay</b>, {WEEKDAY_LONG[day.weekday()]} {day:%d/%m}:", *_late_section(late, now, limit)]
        if due:
            lines += [f"Còn lại hôm nay ({len(due)} việc):", *_bullets([_due_line(task, now, limit) for task in due])]
        elif not late:
            lines.append("Hôm nay không còn hạn nào phải lo.")
        if blocks:
            lines += ["Khối giờ đã định:", *_bullets([_block_line(row, limit) for row in blocks])]
        if routine:
            lines.append(f"Việc thường nhật: {_names(routine, limit)}.")
        if done:
            lines.append(f"Đã xong hôm nay ({len(done)} việc): {_names(done, limit)}.")
        return [*lines, SIGN_OFF]
    return _fitted(build)


def week(store, now):
    """/week: hạn định của 7 ngày kể từ hôm nay, xếp theo từng ngày. Việc lặp hằng ngày gom thành một dòng."""
    today_, last = now.date(), now.date() + timedelta(days=WEEK_DAYS)
    tasks = [task for task in store.list_tasks("all", now) if task["due_at"] and from_text(task["due_at"]).date() < last]
    late = [task for task in tasks if from_text(task["due_at"]) < now and not _is_routine(task)]
    routine = [task for task in tasks if _is_routine(task)]
    days = {}
    for task in tasks:
        if not _is_routine(task) and from_text(task["due_at"]) >= now:
            days.setdefault(from_text(task["due_at"]).date(), []).append(task)
    total = sum(map(len, days.values()))

    def build(limit):
        lines = [f"<b>Tâu Bệ hạ, hạn định 7 ngày tới</b> ({today_:%d/%m} – {last - timedelta(days=1):%d/%m}):", *_late_section(late, now, limit)]
        for day in sorted(days):
            lines += [f"<b>{_day_title(day, today_)}</b> ({len(days[day])} việc)",
                      *_bullets([f"{_name(task, limit)}{_moment(task)}" for task in days[day]])]
        lines.append(f"Tổng cộng {total} việc đến hạn trong 7 ngày tới." if total else "7 ngày tới chưa có hạn nào.")
        if routine:
            lines.append(f"Việc thường nhật: {_names(routine, limit)}.")
        return [*lines, SIGN_OFF]
    return _fitted(build)


def _pomodoro_line(store, now):
    from . import pomodoro
    state, focus = pomodoro.read(store), store.focus_stats(now)
    parts = []
    if state.end:
        parts.append(f"đang {pomodoro.PHASE_NAMES[state.phase].lower()}, còn {humanize(state.end - now)}")
    elif state.left:
        parts.append(f"đang tạm dừng, còn {humanize(timedelta(seconds=state.left))}")
    if focus["count"]:
        parts.append(f"hôm nay đã xong {focus['count']} phiên ({humanize(timedelta(minutes=focus['minutes']))})")
    return f"Pomodoro: {'; '.join(parts)}." if parts else ""


def _next_line(task, now, limit):
    label = when_label(task["due_at"], task["all_day"], now)
    label = label[0].lower() + label[1:] if label.startswith(("Hôm", "Ngày")) else label
    return f"Mốc tiếp theo: <b>{_name(task, limit)}</b>, hạn {label}, còn {humanize(from_text(task['due_at']) - now)}."


def progress(store, now):
    """/rp: báo cáo giữa ngày theo thời gian thực, gồm tiến độ, việc đã xong, việc còn lại, việc đang làm và mốc kế tiếp."""
    stats = store.stats(now)
    late, current = store.summary_tasks(now)
    done = store.list_tasks("done_today", now)
    block = active_block(store.scheduled_tasks(), now)
    nearest, pomodoro_line = store.nearest_deadline(now), _pomodoro_line(store, now)
    if stats["planned"]:
        summary = f"Đã xong {stats['done_today']}/{stats['planned']} việc của hôm nay ({round(stats['rate'] * 100)}%)"
    else:
        summary = f"Đã xong {len(done)} việc" if done else "Hôm nay chưa có việc nào đến hạn"
    summary += (f", còn {len(current)} việc" if current else "") + (f", {len(late)} việc đã trễ" if late else "") + "."
    if late:
        closing = "Thần cúi xin Bệ hạ lo các việc trễ trước."
    elif done and not current:
        closing = "Việc trong ngày đã xong cả, thần mừng khôn xiết!"
    elif stats["rate"] is not None and stats["rate"] >= 0.5:
        closing = "Đã quá nửa chặng đường, xin Bệ hạ giữ vững nhịp này."
    else:
        closing = SIGN_OFF

    def build(limit):
        lines = [f"<b>Tâu Bệ hạ, tình hình đến {now:%H:%M} hôm nay</b>", summary]
        if done:
            lines += [f"Đã xong ({len(done)} việc):", *_bullets([f"{_name(task, limit)} ({task['done_at'][11:16]})" for task in done])]
        if current:
            lines += [f"Còn lại ({len(current)} việc):", *_bullets([_due_line(task, now, limit) for task in current])]
        lines += _late_section(late, now, limit)
        if block:
            task, _start, end = block
            lines.append(f"Đang làm: <b>{_name(task, limit)}</b>, khối giờ còn {humanize(end - now)}.")
        if pomodoro_line:
            lines.append(pomodoro_line)
        if nearest:
            lines.append(_next_line(nearest, now, limit))
        return [*lines, closing]
    return _fitted(build)
