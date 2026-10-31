"""Quick Add: hiểu câu tiếng Việt tự nhiên kiểu Todoist.

    "Nộp báo cáo mai 9h !1 #công-việc"  -> hạn ngày mai 09:00, ưu tiên cao, tag Công việc
    "Tập gym t2 18h hằng tuần ~60p"     -> thứ Hai 18:00, lặp hằng tuần, khối 60 phút

Gõ có dấu thì khớp đúng dấu ("thu 5 triệu" không phải thứ Năm); gõ không dấu
("nop bao cao mai 9h") thì khớp theo bản bỏ dấu. Hai chuỗi này luôn dài bằng nhau
nên vị trí khớp dùng được để cắt phần đã hiểu ra khỏi tên việc.
"""
import re
import unicodedata
from datetime import date, datetime, timedelta

from .schedule import ALL_DAY_TIME, days_in_month, to_text, when_label, RECUR_LABELS

_WEEKDAY_WORDS = {"hai": 0, "ba": 1, "tu": 2, "nam": 3, "sau": 4, "bay": 5, "2": 0, "3": 1, "4": 2, "5": 3, "6": 4, "7": 5}
_WEEKDAY = r"(?:thứ (?P<wd>hai|ba|tư|năm|sáu|bảy|[2-7])|t(?P<wn>[2-7])|(?P<cn>cn|chủ nhật))"
_PART_HOURS = {"sang": 9, "trua": 12, "chieu": 15, "toi": 20, "dem": 22}
_PART = r"(?P<part>sáng|trưa|chiều|tối|đêm)"
_UNIT_MINUTES = {"p": 1, "ph": 1, "phut": 1, "m": 1, "h": 60, "g": 60, "gio": 60, "tieng": 60,
                 "ngay": 1440, "tuan": 10080}


def _strip_marks(text):
    """Bỏ dấu, giữ nguyên hoa/thường và độ dài chuỗi."""
    return "".join({"đ": "d", "Đ": "D"}.get(char) or unicodedata.normalize("NFD", char)[0] for char in text)


def _lower(text):
    return "".join(char.lower() if len(char.lower()) == 1 else char for char in text)


def _fold(text):
    return _lower(_strip_marks(text))


class _Rule:
    """Một mẫu viết có dấu, tự sinh thêm bản không dấu."""

    def __init__(self, pattern):
        wrapped = rf"(?<![\w/:-])(?:{pattern})(?![\w/-])"
        self.strict = re.compile(wrapped)
        self.loose = re.compile(_strip_marks(wrapped))


_TAG = re.compile(r"(?<!\S)#([^\s#!~]+)")
_PRIORITY = re.compile(r"(?<!\S)!(?:(?P<n>[123])|(?P<word>cao|vừa|vua|thấp|thap)|(?P<bang>!{0,2}))(?!\S)")
_BLOCK = re.compile(r"(?<!\S)~(?:(\d{1,2})\s?(?:h|g)\s?(\d{1,2})?(?:p|m)?|(\d{1,3})\s?(?:p|m|ph)?)(?!\S)")
_RECUR_WEEKDAY = _Rule(rf"mỗi {_WEEKDAY}")
_RECUR = _Rule(r"(?P<daily>hằng ngày|hàng ngày|mỗi ngày|daily)|(?P<weekdays>ngày thường|t2-t6)"
               r"|(?P<weekly>hằng tuần|hàng tuần|mỗi tuần|weekly)|(?P<monthly>hằng tháng|hàng tháng|mỗi tháng|monthly)")
_RELATIVE = _Rule(r"(?<!tuần )(?:sau |trong )(?P<a>\d{1,3}) ?(?P<ua>phút|ph|p|m|tiếng|giờ|g|h|ngày|tuần)"
                  r"|(?P<b>\d{1,3}) ?(?P<ub>phút|ph|p|tiếng|giờ|ngày|tuần) nữa")
_DAYPART_DATE = _Rule(rf"{_PART} (?P<day>nay|mai|mốt|{_WEEKDAY})")
_NAMED_DATE = _Rule(r"(?P<today>hôm nay)|(?P<tomorrow>ngày mai)|(?P<after>ngày mốt|ngày kia|mốt)"
                    r"|(?P<nextweek>tuần sau|tuần tới)|(?P<weekend>cuối tuần)|(?P<monthend>cuối tháng)")
_BARE_TOMORROW = _Rule(r"mai")
_NUMERIC_DATE = _Rule(r"(?:ngày )?(?P<d>\d{1,2})[/-](?P<m>\d{1,2})(?:[/-](?P<y>\d{2,4}))?")
_DAY_OF_MONTH = _Rule(r"ngày (?P<d>\d{1,2})")
_WEEKDAY_DATE = _Rule(rf"{_WEEKDAY}(?P<next> tuần (?:sau|tới))?")
_TIME = _Rule(r"(?:(?P<h1>\d{1,2}):(?P<m1>\d{2})"
              r"|(?P<h2>\d{1,2}) ?(?:h|g|giờ)(?: ?(?P<m2>\d{1,2})(?: ?(?:p|ph|phút))?)?"
              r"|(?P<h3>\d{1,2}) ?(?P<ap>am|pm))"
              r"(?: (?P<tp>sáng|trưa|chiều|tối|đêm)(?P<tonight> nay)?)?")
_KIN_BEFORE_MAI = ("chị ", "anh ", "em ", "cô ", "chú ", "bác ", "bạn ", "ông ", "bà ", "dì ", "thầy ")
_CONNECTORS = re.compile(r"(?:(?<=\s)|^)(?<!gia )(?:(?:vào lúc|vao luc|vào|vao|lúc|luc|trước|truoc|hạn|han|deadline)\s+)+(?=\x00)",
                         re.IGNORECASE)


def _weekday_of(match):
    return 6 if match["cn"] else _WEEKDAY_WORDS[_fold(match["wd"] or match["wn"])]


class _Parser:
    def __init__(self, text, now):
        self.text = unicodedata.normalize("NFC", text)
        self.now = now
        self.today = now.date()
        folded = _fold(self.text)
        self.has_marks = folded != self.text.lower()
        self.subject = _lower(self.text) if self.has_marks else folded
        self.spans = []
        self.result = {"title": "", "due_at": None, "all_day": 0, "priority": 0, "tags": [], "recur": "",
                       "block_start": None, "block_minutes": 0}
        self.day = None
        self.moment = None  # (giờ, phút)
        self.exact = None  # thời điểm chính xác, từ "sau 30p"
        self.named_weekday = None  # thứ trong tuần được nêu trần, chưa kèm "tuần sau"

    # Các tiện ích quét chuỗi -------------------------------------------------

    def _free(self, match):
        return not any(start < match.end() and match.start() < end for start, end in self.spans)

    def _take(self, match):
        self.spans.append(match.span())

    def _search(self, rule):
        pattern = rule.strict if self.has_marks else rule.loose
        for match in pattern.finditer(self.subject):
            if self._free(match):
                return match
        return None

    # Từng loại thông tin -----------------------------------------------------

    def _tags(self):
        for match in _TAG.finditer(self.text):
            self.result["tags"].append(match[1])
            self._take(match)

    def _priority(self):
        match = _PRIORITY.search(self.subject)
        if not match:
            return
        if match["n"]:
            level = 4 - int(match["n"])
        elif match["word"]:
            level = {"cao": 3, "vua": 2, "thap": 1}[_fold(match["word"])]
        else:
            level = len(match["bang"]) + 1
        self.result["priority"] = level
        self._take(match)

    def _block(self):
        match = _BLOCK.search(self.subject)
        if match:
            minutes = int(match[3]) if match[3] else int(match[1]) * 60 + int(match[2] or 0)
            if minutes:
                self.result["block_minutes"] = minutes
                self._take(match)

    def _recur(self):
        match = self._search(_RECUR_WEEKDAY)
        if match:
            self.result["recur"] = "weekly"
            self.day = self._next_weekday(_weekday_of(match))
            self._take(match)
            return
        match = self._search(_RECUR)
        if match:
            self.result["recur"] = next(name for name in ("daily", "weekdays", "weekly", "monthly") if match[name])
            self._take(match)

    def _relative(self):
        match = self._search(_RELATIVE)
        if not match:
            return
        minutes = int(match["a"] or match["b"]) * _UNIT_MINUTES[_fold(match["ua"] or match["ub"])]
        target = self.now + timedelta(minutes=minutes)
        if minutes >= 1440:
            self.day = target.date()
        else:
            self.exact = target
        self._take(match)

    def _next_weekday(self, weekday):
        return self.today + timedelta(days=(weekday - self.today.weekday() - 1) % 7 + 1)

    def _daypart_date(self):
        match = self._search(_DAYPART_DATE)
        if not match:
            return
        word = _fold(match["day"])
        if word == "nay":
            self.day = self.today
        elif word == "mai":
            self.day = self.today + timedelta(days=1)
        elif word == "mot":
            self.day = self.today + timedelta(days=2)
        else:
            self.day = self._next_weekday(_weekday_of(match))
        self.moment = (_PART_HOURS[_fold(match["part"])], 0)
        self._take(match)

    def _named_date(self):
        match = self._search(_NAMED_DATE)
        if not match:
            return
        if match["today"]:
            self.day = self.today
        elif match["tomorrow"]:
            self.day = self.today + timedelta(days=1)
        elif match["after"]:
            self.day = self.today + timedelta(days=2)
        elif match["nextweek"]:
            self.day = self.today + timedelta(days=7 - self.today.weekday())
        elif match["weekend"]:
            self.day = self.today + timedelta(days=(5 - self.today.weekday()) % 7)
        else:
            self.day = self.today.replace(day=days_in_month(self.today.year, self.today.month))
        self._take(match)

    def _bare_tomorrow(self):
        """'mai' đứng một mình: tránh nhầm tên riêng như "chị Mai", "gọi Mai"."""
        match = self._search(_BARE_TOMORROW)
        if not match:
            return
        original = self.text[match.start()]
        before = self.subject[:match.start()]
        kin = _KIN_BEFORE_MAI if self.has_marks else tuple(_fold(word) for word in _KIN_BEFORE_MAI)
        if (original == "M" and match.start() > 0) or before.endswith(kin):
            return
        self.day = self.today + timedelta(days=1)
        self._take(match)

    def _numeric_date(self):
        match = self._search(_NUMERIC_DATE)
        if not match:
            return
        year = int(match["y"]) if match["y"] else self.today.year
        year += 2000 if year < 100 else 0
        try:
            day = date(year, int(match["m"]), int(match["d"]))
            if not match["y"] and day < self.today:
                day = day.replace(year=year + 1)
        except ValueError:
            return  # ngày không tồn tại, ví dụ 31/02: giữ nguyên trong tên việc
        self.day = day
        self._take(match)

    def _day_of_month(self):
        match = self._search(_DAY_OF_MONTH)
        if not match:
            return
        number = int(match["d"])
        if not 1 <= number <= 31:
            return
        year, month = self.today.year, self.today.month
        for _ in range(3):
            if number <= days_in_month(year, month) and date(year, month, number) >= self.today:
                self.day = date(year, month, number)
                self._take(match)
                return
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    def _weekday_date(self):
        match = self._search(_WEEKDAY_DATE)
        if not match:
            return
        weekday = _weekday_of(match)
        if match["next"]:
            monday = self.today + timedelta(days=7 - self.today.weekday())
            self.day = monday + timedelta(days=weekday)
        else:
            self.named_weekday = weekday
            self.day = self._next_weekday(weekday)
        self._take(match)

    def _time(self):
        match = self._search(_TIME)
        if not match:
            return
        hour = int(match["h1"] or match["h2"] or match["h3"])
        minute = int(match["m1"] or match["m2"] or 0)
        part = _fold(match["tp"]) if match["tp"] else ""
        if minute > 59 or hour > 24:
            return
        leading_zero = (match["h1"] or "").startswith("0")
        if match["ap"]:
            hour = hour % 12 + (12 if match["ap"] == "pm" else 0)
        elif part in ("chieu", "toi", "dem"):
            if hour == 12 and part == "dem":
                hour, minute = 23, 59
            elif hour < 12:
                hour += 12
        elif part == "sang" and hour == 12:
            hour = 0
        elif not part and 1 <= hour <= 6 and not leading_zero:
            hour += 12  # "họp lúc 2h" nghĩa là 14:00, gần như không ai hẹn 2 giờ sáng
        self.moment = (hour % 24, minute)
        if match["tonight"]:
            self.day = self.today
        self._take(match)

    # Tổng hợp ---------------------------------------------------------------

    def _resolve(self):
        if self.exact:
            self.result["due_at"] = to_text(self.exact)
            return
        if self.day is None and self.moment is None and self.result["recur"]:
            self.day = self._first_recur_day()
        if self.day is None and self.moment is None:
            return
        if self.day is None:
            candidate = datetime(self.today.year, self.today.month, self.today.day, *self.moment)
            if candidate <= self.now:
                candidate += timedelta(days=1)
            if self.result["recur"] == "weekdays":
                while candidate.weekday() > 4:
                    candidate += timedelta(days=1)
            self.result["due_at"] = to_text(candidate)
            return
        if self.moment is None:
            self.result["due_at"] = f"{self.day.isoformat()} {ALL_DAY_TIME}"
            self.result["all_day"] = 1
            return
        if self.named_weekday == self.today.weekday():
            # "t7 20h" nói ngay trong thứ Bảy, khi 20:00 chưa qua, nghĩa là hôm nay.
            if datetime(self.today.year, self.today.month, self.today.day, *self.moment) > self.now:
                self.day = self.today
        self.result["due_at"] = to_text(datetime(self.day.year, self.day.month, self.day.day, *self.moment))

    def _first_recur_day(self):
        day = self.today
        if self.result["recur"] == "weekdays":
            while day.weekday() > 4:
                day += timedelta(days=1)
        return day

    def _title(self):
        chars = list(self.text)
        for start, end in sorted(self.spans):
            chars[start] = "\x00"
            for index in range(start + 1, end):
                chars[index] = ""
        cleaned = _CONNECTORS.sub("", "".join(chars)).replace("\x00", " ")
        cleaned = " ".join(cleaned.split()).strip(" ,;-–")
        self.result["title"] = cleaned or " ".join(self.text.split())

    def run(self):
        self._tags()
        self._priority()
        self._block()
        self._recur()
        self._relative()
        self._numeric_date()
        self._time()  # trước _daypart_date: "5h sáng mai" là 5:00, không phải buổi sáng mặc định
        if self.moment is None:
            self._daypart_date()
        self._day_of_month()
        self._weekday_date()
        self._named_date()
        self._bare_tomorrow()
        self._resolve()
        if self.result["block_minutes"] and self.result["due_at"] and not self.result["all_day"]:
            self.result["block_start"] = self.result["due_at"]
        self._title()
        return self.result


def parse(text, now=None):
    """Tách một câu thành các trường của task, sẵn sàng đưa vào Store.add_task()."""
    return _Parser(text, now or datetime.now()).run()


def parse_when(text, now=None):
    """Hiểu một mốc thời gian đơn lẻ (ô Hạn trong giao diện): (due_at, all_day) hoặc None."""
    result = parse(text, now)
    return (result["due_at"], result["all_day"]) if result["due_at"] else None


def describe(parsed, now=None, tag_label=str):
    """Mô tả ngắn phần đã hiểu, để người dùng thấy trước khi Enter."""
    now = now or datetime.now()
    parts = []
    if parsed["due_at"]:
        parts.append(when_label(parsed["due_at"], parsed["all_day"], now))
    if parsed["priority"]:
        parts.append({1: "Ưu tiên thấp", 2: "Ưu tiên vừa", 3: "Ưu tiên cao"}[parsed["priority"]])
    if parsed["recur"]:
        parts.append(RECUR_LABELS[parsed["recur"]])
    if parsed["block_minutes"]:
        parts.append(f"Khối {parsed['block_minutes']} phút")
    parts.extend(f"#{tag_label(name)}" for name in parsed["tags"])
    return " · ".join(parts)


def tag_prefix(text):
    """Phần tag đang gõ dở ở cuối câu: 'Họp #hoc' -> 'hoc'. Không có thì trả về None."""
    last = text.rsplit(None, 1)[-1] if text.strip() and not text[-1].isspace() else ""
    return last[1:] if last.startswith("#") else None
