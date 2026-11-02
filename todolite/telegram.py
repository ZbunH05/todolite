"""Bot Telegram: tờ tấu công việc mỗi ngày, lời lẽ của một vị quan dâng lên hoàng đế.

Tờ tấu có năm phần: lời mở, báo cáo ngày, hạn định, thuận thiên và kiêng kỵ, lời cáo lui. Dòng đầu
nói ngay số việc để đọc được từ thông báo trên điện thoại. Giọng văn theo ngữ cảnh của ngày: việc
trễ thì can gián, việc gấp thì báo khẩn, ngày rảnh thì tụng ca, ngày sinh thì chúc thọ.

Module này không được agent nạp: phần lịch và dữ liệu xem ngày tốn thêm nhiều MB RAM, trong khi
bản tin chỉ gửi mỗi ngày một lần. Agent chạy `run.pyw --telegram` như một tiến trình riêng, sống
vài giây rồi thoát. Nhờ vậy agent vẫn nhẹ, còn lỗi mạng không bao giờ làm nghẽn vòng lặp của nó.
"""
import time
from collections import namedtuple
from datetime import date, datetime, timedelta

from . import almanac, daybook, lunar
from .bot import Bot, ensure_commands
from .db import Store
from .paths import log
from .report import (MAX_LATE_ITEMS, MAX_LIST_ITEMS, MESSAGE_LIMIT, TITLE_LENGTHS, _block_line, _bullets, _is_routine, _late_line, _length,
                     _mid_sentence, _moment, _name, _upcoming_line, _within_limit)
from .schedule import WEEKDAY_LONG, WEEKDAY_SHORT, from_text
from .web import ApiError
from .win32 import acquire_mutex

SEND_ATTEMPTS = 4
RETRY_DELAY = 15  # giây: lúc PC vừa bật, mạng thường chưa sẵn sàng ngay
MAX_RETRY_DELAY = 120
SEND_MUTEX = "Local\\TodoLite.Telegram"

UPCOMING_DAYS = 14
NEAR_DAYS = 3  # hạn gần thế này thì lời mở nhắc trước dù hôm nay chưa có việc
HEAVY_LATE = 5  # từ số việc trễ này, lời tấu chuyển sang giọng liều chết can gián
MAX_ADVICE_ITEMS = 6
MAX_CLASHES = 3

LATE_TONES = ("Thần phận mỏng tài hèn, biết lời ngay trái tai nhưng không dám giấu, kính dâng tờ tấu {session}.",
              "Thần trộm nghĩ, việc để lâu ắt sinh biến, nên liều dâng tờ tấu {session}.",
              "Thần kính dâng tờ tấu {session}, cúi xin Bệ hạ thánh minh soi xét.")
HEAVY_TONE = "Thần ngu muội, biết dâng lời này ắt phạm tội muôn chết, nhưng thà chịu búa rìu phủ việt cũng không nỡ đứng nhìn việc nước ùn ứ."
URGENT_TONES = ("Quan trạm phi ngựa lưu tinh báo về kinh, thần không dám chậm trễ, kính dâng tờ tấu {session}.",
                "Thần cúi rạp kính cẩn tấu trình, xin Bệ hạ xem qua tờ tấu {session}.",
                "Thần trộm nghĩ việc hệ trọng chớ để lỡ thời, kính dâng tờ tấu {session}.")
NEAR_TONE = "Trong ngày tạm yên, nhưng hạn kế tiếp chỉ còn {left} ngày, thần xin tấu trước để Bệ hạ liệu định."
CALM_TONES = ("Nhờ thánh đức của Bệ hạ, thiên hạ thái bình, trong triều vô sự.",
              "Nay mưa thuận gió hoà, bách tính an cư lạc nghiệp, thảy đều nhờ thánh đức của Bệ hạ.",
              "Ân trạch của Bệ hạ thấm nhuần muôn nơi, trong triều hôm nay yên ổn.")
BIRTHDAY_TONE = "Hôm nay là ngày Vạn thọ thánh tiết của Bệ hạ, thần cùng trăm quan múa lạy dưới bệ ngọc, mừng vui khôn xiết."
FESTIVAL_TONE = "Nhân dịp {event}, thần cúi lạy dưới đan trì, kính dâng tờ tấu {session}."
WISHES = ("Kính chúc Bệ hạ long thể an khang, quốc thái dân an.", "Nguyện Bệ hạ thánh thể vạn an, muôn dân no ấm, quốc thái dân an.",
          "Cầu chúc Bệ hạ long thể khang kiện, vạn tuế, vạn tuế, vạn vạn tuế, quốc thái dân an.",
          "Nguyện Bệ hạ mạnh khoẻ trường thọ, xã tắc đời đời hưng thịnh, quốc thái dân an.")
BIRTHDAY_WISH = "Kính chúc Bệ hạ thọ sánh ngang trời đất, uy danh chấn động bốn phương, quốc thái dân an."
SIGN_OFFS = ("Thần kính tấu!", "Thần dập đầu kính tấu!", "Thần muôn ngàn lần dập đầu, kính tấu!")

Docket = namedtuple("Docket", "late today routine blocks upcoming clashes")


def _pick(options, day):
    """Đổi lời theo ngày để đọc mỗi sáng không thấy lặp."""
    return options[day.toordinal() % len(options)]


def _session(hour):
    """Tờ tấu có thể đi lúc PC vừa bật, nên gọi tên buổi theo giờ thật."""
    return "sớm nay" if hour < 11 else "trưa nay" if hour < 14 else "chiều nay" if hour < 18 else "tối nay"


def _clashes(tasks):
    """Những việc đã hẹn mà rơi đúng vào ngày kiêng loại việc đó."""
    found = []
    for task in tasks:
        day = from_text(task["due_at"]).date()
        clash = daybook.clash_of(task["title"], day)
        if clash:
            found.append((task, day, clash))
    return found


def _docket(store, now):
    """Gom việc cần tấu. Việc lặp hằng ngày là nếp thường nhật, không tính là hạn để khỏi báo động giả mỗi ngày."""
    overdue, today = store.summary_tasks(now)
    last_day = now.date() + timedelta(days=UPCOMING_DAYS)
    upcoming = [task for task in store.list_tasks("upcoming", now) if not _is_routine(task) and from_text(task["due_at"]).date() <= last_day]
    due = [task for task in today if not _is_routine(task)]
    return Docket([task for task in overdue if not _is_routine(task)], due, [task for task in overdue + today if _is_routine(task)],
                  store.blocks_today(now), upcoming, _clashes(due + upcoming))


def _birth(store):
    stored = store.setting("birth_date")
    return date.fromisoformat(stored) if stored else None


def _is_birthday(birth, day):
    """Ngày sinh tính cả theo dương lịch lẫn âm lịch, vì nhiều nhà vẫn mừng theo ngày âm."""
    if birth is None:
        return False
    born, current = lunar.solar_to_lunar(birth), lunar.solar_to_lunar(day)
    return (birth.month, birth.day) == (day.month, day.day) or ((born.month, born.day) == (current.month, current.day) and not current.leap)


def _headline(docket):
    late, due = len(docket.late), len(docket.today)
    if late and due:
        return f"hôm nay có {due} việc đến hạn, {late} việc đã trễ."
    if late:
        return f"đã có {late} việc trễ hạn."
    return f"hôm nay có {due} việc đến hạn." if due else "hôm nay không có việc đến hạn."


def _tone(docket, now, birthday):
    """Lời mở theo ngữ cảnh, việc càng cấp bách càng được ưu tiên."""
    day, session = now.date(), _session(now.hour)
    events = almanac.events_on(day)
    if birthday:
        return BIRTHDAY_TONE
    if events:
        return FESTIVAL_TONE.format(event=events[0], session=session)
    if len(docket.late) >= HEAVY_LATE:
        return HEAVY_TONE
    if docket.late:
        return _pick(LATE_TONES, day).format(session=session)
    if docket.today:
        return _pick(URGENT_TONES, day).format(session=session)
    left = (from_text(docket.upcoming[0]["due_at"]).date() - day).days if docket.upcoming else UPCOMING_DAYS
    return NEAR_TONE.format(left=left) if left <= NEAR_DAYS else _pick(CALM_TONES, day)


def _opening(docket, now, birthday):
    return [f"<b>Muôn tâu Bệ hạ,</b> {_headline(docket)}", _tone(docket, now, birthday)]


def _day_section(now, reading):
    day = now.date()
    converted = lunar.solar_to_lunar(day)
    lines = ["<b>Báo cáo ngày</b>",
             f"{WEEKDAY_LONG[day.weekday()]}, {day:%d/%m/%Y}, tức {lunar.lunar_text(converted)} năm {lunar.year_can_chi(converted.year)}.",
             f"Ngày {lunar.day_can_chi(day)}, tháng {lunar.month_can_chi(converted.month, converted.year)}, tiết {lunar.solar_term(day)}."]
    events = almanac.events_on(day)
    if events:
        lines.append(f"Hôm nay là {', '.join(events)}.")
    lines.append(f"Thần xem sách lịch, hôm nay là <b>{reading.title.lower()}</b>: {_mid_sentence(reading.reason)}.")
    return lines


def _deadline_section(docket, now, limit):
    lines = ["<b>Hạn định</b>"]
    if docket.late:
        lines.append(f"Đã trễ ({len(docket.late)} việc):")
        lines.extend(_bullets([_late_line(task, now, limit) for task in docket.late], MAX_LATE_ITEMS))
    if docket.today:
        lines.append(f"Hôm nay ({len(docket.today)} việc):")
        lines.extend(_bullets([f"<b>{_name(task, limit)}</b>{_moment(task)}" for task in docket.today]))
    else:
        lines.append("Hôm nay không có việc đến hạn.")
    if docket.blocks:
        lines.append("Khối giờ đã định:")
        lines.extend(_bullets([_block_line(row, limit) for row in docket.blocks]))
    if docket.routine:
        lines.append(f"Việc thường nhật: {', '.join(_mid_sentence(_name(task, limit)) for task in docket.routine[:MAX_LIST_ITEMS])}.")
    if docket.upcoming:
        lines.append(f"{UPCOMING_DAYS} ngày tới ({len(docket.upcoming)} việc):")
        lines.extend(_bullets([_upcoming_line(task, now.date(), limit) for task in docket.upcoming]))
    else:
        lines.append(f"{UPCOMING_DAYS} ngày tới chưa có hạn nào.")
    return lines


def _works(items):
    names = [_mid_sentence(item.task) for item in items[:MAX_ADVICE_ITEMS]]
    extra = len(items) - len(names)
    return "; ".join(names) + (f" và {extra} việc khác" if extra > 0 else "")


def _clash_line(task, day, clash, today, limit):
    when = "hôm nay" if day == today else f"ngày {day:%d/%m}"
    line = f"<b>{_name(task, limit)}</b> {when} phạm {', '.join(clash.reasons[:2])}, kiêng {clash.label}."
    other = daybook.nearest_clear_day(day, clash.work, today)
    return f"{line} Ngày gần nhất không vướng là {WEEKDAY_SHORT[other.weekday()]} {other:%d/%m}." if other else line


def _advice_section(docket, reading, now, birth, limit):
    day = now.date()
    hours = ", ".join(f"{slot.name} {slot.start}–{slot.end}h" for slot in daybook.hours_of(day) if slot.good)
    lines = ["<b>Thuận thiên, kiêng kỵ</b>",
             f"Việc thuận thiên: {_works(reading.do)}." if reading.do else "Hôm nay không có việc nên khởi sự, xin Bệ hạ chỉ lo việc thường nhật.",
             f"Việc kiêng kỵ: {_works(reading.avoid)}." if reading.avoid else "Hôm nay không có việc phải kiêng.",
             f"Giờ hoàng đạo: {hours}."]
    note = daybook.age_note(day, birth) if birth else None
    if note:
        lines.append(f"{note[1].replace('của bạn', 'của Bệ hạ')}.")
    if docket.clashes:
        lines.append("Ngu ý của thần, các việc này nên cân nhắc:")
        lines.extend(_bullets([_clash_line(task, when, clash, day, limit) for task, when, clash in docket.clashes], MAX_CLASHES))
    return lines


def _closing(docket, now, birthday):
    asks = []
    if docket.late:
        asks.append(f"{len(docket.late)} việc đã trễ nên làm ngay hay dời hạn")
    if docket.clashes:
        asks.append(f"{len(docket.clashes)} việc vướng điều kiêng có đổi ngày hay không")
    if asks:
        request = f"Thần xin cáo lui, cúi mong Bệ hạ thánh minh định đoạt: {', '.join(asks)}."
    elif docket.today:
        request = "Thần xin cáo lui, cúi mong Bệ hạ thánh minh định liệu các việc đến hạn hôm nay."
    else:
        request = "Thần xin cáo lui, chờ thánh ý của Bệ hạ."
    return [request, BIRTHDAY_WISH if birthday else _pick(WISHES, now.date()), _pick(SIGN_OFFS, now.date())]


def build_brief(store, now):
    """Tờ tấu hôm nay dạng HTML của Telegram. Tên việc đã được thoát ký tự đặc biệt."""
    docket, reading, birth = _docket(store, now), daybook.read_day(now.date()), _birth(store)
    birthday = _is_birthday(birth, now.date())
    for limit in TITLE_LENGTHS:
        sections = (_opening(docket, now, birthday), _day_section(now, reading), _deadline_section(docket, now, limit),
                    _advice_section(docket, reading, now, birth, limit), _closing(docket, now, birthday))
        text = "\n\n".join("\n".join(section) for section in sections)
        if _length(text) <= MESSAGE_LIMIT:
            return text
    return _within_limit(text)


def send_brief(store, now):
    Bot(store.secret("telegram_token"), store.setting("telegram_api_url")).send(store.setting("telegram_chat_id"), build_brief(store, now))


def _give_up(store, now, message):
    store.set_setting("telegram_status", f"{now:%H:%M %d/%m}: {message}")
    log(f"Telegram: {message}")
    return False


def send_scheduled(store=None, now=None, wait=time.sleep):
    """Gửi bản tin tự động, chạy trong tiến trình riêng. Trả về True nếu đã gửi."""
    store = store or Store(cache_kb=128)
    now = now or datetime.now()
    today = now.date().isoformat()
    if store.setting("telegram_last_sent") == today:
        return False  # tiến trình khác vừa gửi xong
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            send_brief(store, now)
        except ApiError as error:
            if error.permanent:
                store.set_setting("telegram_failed_on", today)  # lỗi cấu hình: mai mới thử lại
                return _give_up(store, now, f"Không gửi được. {error}")
            if attempt == SEND_ATTEMPTS:
                return _give_up(store, now, f"Chưa gửi được, sẽ thử lại. {error}")
            wait(min(max(RETRY_DELAY, error.retry_after), MAX_RETRY_DELAY))
        else:
            store.set_setting("telegram_last_sent", today)
            store.set_setting("telegram_status", f"{now:%H:%M %d/%m}: Đã gửi bản tin")
            ensure_commands(store, Bot(store.secret("telegram_token"), store.setting("telegram_api_url")))
            return True


def main():
    """Điểm vào của tiến trình gửi: `run.pyw --telegram`."""
    mutex = acquire_mutex(SEND_MUTEX)
    if mutex is not None:
        send_scheduled()
