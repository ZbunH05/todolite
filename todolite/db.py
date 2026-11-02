"""Lưu trữ cục bộ bằng SQLite.

WAL cho phép agent và giao diện (hai tiến trình) đọc/ghi cùng lúc mà không khoá nhau.
Mọi thay đổi schema đi qua MIGRATIONS: mỗi hàm nâng lên đúng một phiên bản, DB mới cũng
chạy lần lượt các bước đó nên đường nâng cấp luôn được kiểm chứng.
"""
import os
import sqlite3
from datetime import datetime, timedelta

from .paths import DB_PATH
from .schedule import block_window, from_text, next_occurrence, to_text

BACKUP_KEEP = 7
TAG_SEPARATOR = "\x1f"

TAG_PRESETS = (("Công việc", "#4DA3FF"), ("Học tập", "#B58CFF"), ("Gia đình", "#FF7EB6"),
               ("Cá nhân", "#2FD9C4"), ("Sức khoẻ", "#62E58C"), ("Tài chính", "#FFC53D"))
TAG_COLORS = tuple(color for _, color in TAG_PRESETS) + ("#FF9B54", "#FF7B72", "#56D4FF", "#C3E85A")

SCHEMA_V1 = """
CREATE TABLE tasks (
    id            INTEGER PRIMARY KEY,
    title         TEXT    NOT NULL,
    notes         TEXT    NOT NULL DEFAULT '',
    tag           TEXT    NOT NULL DEFAULT '',
    priority      INTEGER NOT NULL DEFAULT 0,    -- 0 không, 1 thấp, 2 vừa, 3 cao
    due_at        TEXT,                          -- 'YYYY-MM-DD HH:MM', giờ địa phương
    all_day       INTEGER NOT NULL DEFAULT 0,    -- 1: chỉ có ngày, due_at đặt 23:59
    remind        TEXT    NOT NULL DEFAULT '',   -- '30,15': số phút nhắc trước hạn
    recur         TEXT    NOT NULL DEFAULT '',   -- daily|weekdays|weekly|monthly:ngày
    block_start   TEXT,                          -- khối thời gian: thời điểm bắt đầu
    block_minutes INTEGER NOT NULL DEFAULT 0,    -- khối thời gian: thời lượng
    snooze_until  TEXT,
    prev_id       INTEGER,                       -- lần lặp trước sinh ra task này
    done_at       TEXT,                          -- NULL khi chưa xong
    created_at    TEXT    NOT NULL
);
CREATE INDEX idx_tasks_open ON tasks(done_at, due_at);
CREATE TABLE checkpoints (
    id       INTEGER PRIMARY KEY,
    task_id  INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title    TEXT    NOT NULL,
    done     INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_checkpoints_task ON checkpoints(task_id, position);
CREATE TABLE sent_reminders (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind    TEXT    NOT NULL,
    stamp   TEXT    NOT NULL,
    PRIMARY KEY (task_id, kind, stamp)
) WITHOUT ROWID;
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
"""

SCHEMA_V2 = """
CREATE TABLE tags (
    id       INTEGER PRIMARY KEY,
    name     TEXT    NOT NULL,
    key      TEXT    NOT NULL UNIQUE,            -- tên đã bỏ dấu: chống tag trùng như 'sức khoẻ', 'suc-khoe'
    color    TEXT    NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE task_tags (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
) WITHOUT ROWID;
CREATE INDEX idx_task_tags_tag ON task_tags(tag_id);
"""

SCHEMA_V3 = """
CREATE TABLE focus_sessions (
    id         INTEGER PRIMARY KEY,
    task_id    INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    started_at TEXT    NOT NULL,                 -- 'YYYY-MM-DD HH:MM:SS', giờ địa phương
    minutes    INTEGER NOT NULL
);
CREATE INDEX idx_focus_started ON focus_sessions(started_at);
"""

DEFAULT_SETTINGS = {
    "theme": "dark",             # light | dark | system
    "text_scale": "1",           # hệ số cỡ chữ, xem TEXT_SCALES trong ui/theme.py
    "summary_time": "07:30",     # PC bật xuyên đêm vẫn nhận tóm tắt mỗi sáng
    "default_remind": "30,15",
    "hotkey": "1",
    "timer_pill": "1",
    "pill_pos": "",
    "last_summary": "",
    "last_maintenance": "",
    "ui_request": "",
    "window": "",
    "calendar_mode": "month",    # week | month
    "telegram_enabled": "1",     # chỉ có tác dụng khi đã nhập token và Chat ID
    "telegram_token": "",        # đã mã hoá bằng DPAPI, xem vault.py
    "telegram_chat_id": "",
    "telegram_api_url": "https://api.telegram.org",
    "telegram_time": "07:30",
    "telegram_on_start": "1",    # gửi ngay khi PC bật lần đầu trong ngày
    "telegram_last_sent": "",
    "telegram_failed_on": "",
    "telegram_status": "",
    "telegram_inbox": "1",       # thêm việc bằng tin nhắn gửi cho bot
    "telegram_inbox_since": "",  # giờ Unix, tin cũ hơn mốc này không thành việc
    "telegram_last_message": "", # 'chat:mã tin' đã xử lý, chống ghi trùng khi Telegram gửi lại
    "telegram_last_added": "",   # các việc của tin gần nhất, dành cho lệnh /huy
    "telegram_commands": "",     # phiên bản menu lệnh đã đăng ký với Telegram, xem bot.COMMANDS
    "ai_url": "https://api.deepseek.com/chat/completions",
    "ai_key": "",                # đã mã hoá bằng DPAPI
    "ai_model": "deepseek-flash",
    "birth_date": "",
    "telegram_remind": "1440,60",  # số phút nhắc trước hạn qua Telegram, rỗng là tắt
    "quote_topics": "",          # chủ đề của Câu nói hôm nay, rỗng là cả sáu chủ đề (xem quotes.py)
    "pomo_focus": "25",          # Pomodoro: số phút của từng loại phiên, xem pomodoro.py
    "pomo_short": "5",
    "pomo_long": "15",
    "pomo_rounds": "4",          # sau từng này phiên tập trung thì nghỉ dài
    "pomo_auto_break": "1",
    "pomo_auto_focus": "0",
    "pomo_phase": "focus",
    "pomo_end": "",              # giờ hết phiên khi đồng hồ đang chạy
    "pomo_left": "",             # số giây còn lại khi đang tạm dừng
    "pomo_round": "0",           # số phiên tập trung đã xong trong vòng hiện tại
    "pomo_task": "",
    "pomo_notice": "",           # lần chuyển phiên gần nhất 'mốc|tiêu đề|dòng', agent hiện thông báo
}

EDITABLE = frozenset(("title", "notes", "priority", "due_at", "all_day", "remind", "recur",
                      "block_start", "block_minutes", "snooze_until"))

TASK_SELECT = f"""
SELECT t.*, (SELECT COUNT(*) FROM checkpoints c WHERE c.task_id = t.id) AS cp_total,
       (SELECT COALESCE(SUM(c.done), 0) FROM checkpoints c WHERE c.task_id = t.id) AS cp_done,
       (SELECT GROUP_CONCAT(name, char({ord(TAG_SEPARATOR)})) FROM (
            SELECT g.name FROM task_tags k JOIN tags g ON g.id = k.tag_id
            WHERE k.task_id = t.id ORDER BY g.position, g.id)) AS tag_names
FROM tasks t
"""
OPEN_ORDER = " ORDER BY t.due_at IS NULL, t.due_at, t.priority DESC, t.id"


def tag_key(name):
    """Khoá so khớp tag: '#Sức-khoẻ', 'sức khỏe', 'suc_khoe' đều cho 'suc khoe'."""
    import unicodedata  # chỉ nạp khi thực sự tạo tag, agent không cần tới khi nghỉ
    plain = "".join(char for char in unicodedata.normalize("NFD", name) if not unicodedata.combining(char))
    plain = plain.replace("đ", "d").replace("Đ", "D").lower()
    return " ".join(plain.replace("#", " ").replace("-", " ").replace("_", " ").split())


def tag_display(name):
    """'dự-án-lớn' -> 'Dự án lớn'."""
    words = " ".join(name.lstrip("#").replace("-", " ").replace("_", " ").split())
    return words[:1].upper() + words[1:]


def task_tag_names(task):
    return task["tag_names"].split(TAG_SEPARATOR) if task["tag_names"] else []


def _ensure_tag(conn, name):
    """id của tag theo tên, tạo mới nếu chưa có. None nếu tên rỗng."""
    key = tag_key(name)
    if not key:
        return None
    row = conn.execute("SELECT id FROM tags WHERE key=?", (key,)).fetchone()
    if row:
        return row["id"]
    count = conn.execute("SELECT COUNT(*), COALESCE(MAX(position), -1) + 1 FROM tags").fetchone()
    color = TAG_COLORS[count[0] % len(TAG_COLORS)]
    return conn.execute("INSERT INTO tags(name, key, color, position) VALUES(?, ?, ?, ?)",
                        (tag_display(name), key, color, count[1])).lastrowid


def _run_script(conn, script):
    for statement in script.split(";\n"):
        if statement.strip():
            conn.execute(statement)


def _create_schema(conn):
    _run_script(conn, SCHEMA_V1)


def _add_tags(conn):
    """Từ một nhãn tự do trên mỗi task sang tag có màu, mỗi task mang được nhiều tag."""
    _run_script(conn, SCHEMA_V2)
    for position, (name, color) in enumerate(TAG_PRESETS):
        conn.execute("INSERT INTO tags(name, key, color, position) VALUES(?, ?, ?, ?)",
                     (name, tag_key(name), color, position))
    for row in conn.execute("SELECT id, tag FROM tasks WHERE tag <> ''").fetchall():
        conn.execute("INSERT OR IGNORE INTO task_tags(task_id, tag_id) VALUES(?, ?)", (row["id"], _ensure_tag(conn, row["tag"])))
    conn.execute("ALTER TABLE tasks DROP COLUMN tag")


def _add_focus_sessions(conn):
    """Lịch sử các phiên Pomodoro đã xong, để đếm số phiên và số phút tập trung theo ngày."""
    _run_script(conn, SCHEMA_V3)


MIGRATIONS = (_create_schema, _add_tags, _add_focus_sessions)
SCHEMA_VERSION = len(MIGRATIONS)


class Store:
    def __init__(self, path=DB_PATH, cache_kb=2000):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute(f"PRAGMA cache_size=-{cache_kb}")
        self._migrate()

    def _version(self):
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def _migrate(self):
        version = self._version()
        if version > SCHEMA_VERSION:
            raise RuntimeError("Dữ liệu được tạo bởi phiên bản TodoLite mới hơn.")
        if version == SCHEMA_VERSION:
            return
        if version:
            self._backup_to(f"before-schema-{SCHEMA_VERSION}.db")
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            # Agent và giao diện có thể cùng khởi động: đọc lại trong giao dịch để không nâng cấp hai lần.
            for step in MIGRATIONS[self._version():]:
                step(self.conn)
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _backup_folder(self):
        folder = os.path.join(os.path.dirname(self.path), "backups")
        os.makedirs(folder, exist_ok=True)
        return folder

    def _backup_to(self, name):
        target = os.path.join(self._backup_folder(), name)
        if not os.path.exists(target):
            copy = sqlite3.connect(target)
            try:
                self.conn.backup(copy)
            finally:
                copy.close()

    def close(self):
        self.conn.close()

    def data_version(self):
        """Đổi khi tiến trình khác ghi vào DB: giao diện dùng để tự làm mới mà không cần IPC."""
        return self.conn.execute("PRAGMA data_version").fetchone()[0]

    # ---------- Cài đặt ----------

    def setting(self, key):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else DEFAULT_SETTINGS[key]

    def set_setting(self, key, value):
        self.conn.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    def secret(self, key):
        """Đọc giá trị đã mã hoá. Agent chỉ cần biết có hay không nên không gọi hàm này."""
        from .vault import unprotect
        stored = self.setting(key)
        return unprotect(stored) if stored else ""

    def set_secret(self, key, value):
        from .vault import protect
        self.set_setting(key, protect(value) if value else "")

    def take_ui_request(self):
        request = self.setting("ui_request")
        if request:
            self.set_setting("ui_request", "")
        return request

    # ---------- Task ----------

    def _clean(self, fields, current=None):
        unknown = set(fields) - EDITABLE
        if unknown:
            raise ValueError(f"Trường không hợp lệ: {sorted(unknown)}")
        data = dict(fields)
        if "title" in data:
            data["title"] = " ".join(data["title"].split())
            if not data["title"]:
                raise ValueError("Tên việc không được để trống")
        rule = data.get("recur", current["recur"] if current else "")
        due_at = data.get("due_at", current["due_at"] if current else None)
        if rule.startswith("monthly") and due_at and ("recur" in data or "due_at" in data):
            data["recur"] = f"monthly:{from_text(due_at).day}"
        return data

    def add_task(self, title, tags=(), **fields):
        fields.setdefault("remind", self.setting("default_remind"))
        data = self._clean(dict(fields, title=title))
        data["created_at"] = to_text(datetime.now())
        columns, marks = ", ".join(data), ", ".join("?" * len(data))
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            task_id = self.conn.execute(f"INSERT INTO tasks({columns}) VALUES({marks})", tuple(data.values())).lastrowid
            self._link_tags(task_id, tags)
        return task_id

    def update_task(self, task_id, **fields):
        current = self.get_task(task_id)
        if current is None or not fields:
            return
        data = self._clean(fields, current)
        assignments = ", ".join(f"{key}=?" for key in data)
        self.conn.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*data.values(), task_id))

    def delete_task(self, task_id):
        self.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def get_task(self, task_id):
        return self.conn.execute(TASK_SELECT + " WHERE t.id=?", (task_id,)).fetchone()

    def complete_task(self, task_id, now=None):
        """Đánh dấu xong. Việc lặp lại sinh ngay lần kế tiếp: trả về id task mới, nếu có."""
        now = now or datetime.now()
        task = self.get_task(task_id)
        if task is None or task["done_at"]:
            return None
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute("UPDATE tasks SET done_at=?, snooze_until=NULL WHERE id=?", (to_text(now), task_id))
            return self._spawn_next(task, now) if task["recur"] else None

    def _spawn_next(self, task, now):
        base = from_text(task["due_at"]) if task["due_at"] else now
        due = next_occurrence(base, task["recur"], now)
        block_start = None
        if task["block_start"]:
            shifted = from_text(task["block_start"]) + (due - base)
            block_start = to_text(shifted)
        new_id = self.conn.execute(
            "INSERT INTO tasks(title, notes, priority, due_at, all_day, remind, recur, block_start,"
            " block_minutes, prev_id, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (task["title"], task["notes"], task["priority"], to_text(due), task["all_day"],
             task["remind"], task["recur"], block_start, task["block_minutes"], task["id"], to_text(now)),
        ).lastrowid
        self.conn.execute("INSERT INTO checkpoints(task_id, title, position) "
                          "SELECT ?, title, position FROM checkpoints WHERE task_id=?", (new_id, task["id"]))
        self.conn.execute("INSERT INTO task_tags(task_id, tag_id) SELECT ?, tag_id FROM task_tags WHERE task_id=?",
                          (new_id, task["id"]))
        return new_id

    def reopen_task(self, task_id):
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute("UPDATE tasks SET done_at=NULL WHERE id=?", (task_id,))
            self.conn.execute("DELETE FROM tasks WHERE prev_id=? AND done_at IS NULL", (task_id,))

    def snooze(self, task_id, minutes, now=None):
        moment = (now or datetime.now()) + timedelta(minutes=minutes)
        self.conn.execute("UPDATE tasks SET snooze_until=? WHERE id=?", (to_text(moment), task_id))

    def move_on_calendar(self, task_id, kind, delta):
        """Kéo-thả trên lịch. Khối giờ mang theo hạn chót nằm trong nó; hạn ở ngày khác thì đứng yên."""
        task = self.get_task(task_id)
        if task is None:
            return
        fields = {"snooze_until": None}
        window = block_window(task)
        if kind == "block" and window:
            fields["block_start"] = to_text(window[0] + delta)
        if task["due_at"] and (kind == "due" or (window and window[0] <= from_text(task["due_at"]) <= window[1])):
            fields["due_at"] = to_text(from_text(task["due_at"]) + delta)
        self.update_task(task_id, **fields)

    # ---------- Tag ----------

    def tags(self):
        return self.conn.execute(
            "SELECT g.*, (SELECT COUNT(*) FROM task_tags k JOIN tasks t ON t.id = k.task_id "
            "WHERE k.tag_id = g.id AND t.done_at IS NULL) AS n FROM tags g ORDER BY g.position, g.id").fetchall()

    def find_tag(self, name):
        return self.conn.execute("SELECT * FROM tags WHERE key=?", (tag_key(name),)).fetchone()

    def tag_label(self, name):
        """Tên hiển thị của tag: dùng để xem trước khi người dùng gõ #hoc-tap."""
        row = self.find_tag(name)
        return row["name"] if row else tag_display(name)

    def ensure_tag(self, name):
        return _ensure_tag(self.conn, name)

    def _link_tags(self, task_id, names):
        for name in names:
            tag_id = _ensure_tag(self.conn, name)
            if tag_id:
                self.conn.execute("INSERT OR IGNORE INTO task_tags(task_id, tag_id) VALUES(?, ?)", (task_id, tag_id))

    def set_task_tags(self, task_id, names):
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute("DELETE FROM task_tags WHERE task_id=?", (task_id,))
            self._link_tags(task_id, names)

    def rename_tag(self, tag_id, name):
        """Trả về False nếu tên rỗng hoặc trùng tag khác."""
        key = tag_key(name)
        clash = self.conn.execute("SELECT id FROM tags WHERE key=? AND id<>?", (key, tag_id)).fetchone()
        if not key or clash:
            return False
        self.conn.execute("UPDATE tags SET name=?, key=? WHERE id=?", (" ".join(name.split()), key, tag_id))
        return True

    def set_tag_color(self, tag_id, color):
        self.conn.execute("UPDATE tags SET color=? WHERE id=?", (color, tag_id))

    def delete_tag(self, tag_id):
        self.conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))

    # ---------- Khối thời gian ----------

    def start_block(self, task_id, minutes, now=None):
        self.update_task(task_id, block_start=(now or datetime.now()).isoformat(" ", "seconds"), block_minutes=minutes)

    def extend_block(self, task_id, minutes, now=None):
        """Gia hạn khối: nếu khối đã hết thì tính tiếp từ hiện tại."""
        now = now or datetime.now()
        task = self.get_task(task_id)
        if task is None:
            return
        if not task["block_start"]:
            self.start_block(task_id, minutes, now)
            return
        start = from_text(task["block_start"])
        end = max(start + timedelta(minutes=task["block_minutes"]), now) + timedelta(minutes=minutes)
        self.update_task(task_id, block_minutes=round((end - start).total_seconds() / 60))

    def end_block(self, task_id):
        self.update_task(task_id, block_start=None)

    # ---------- Pomodoro ----------

    def add_focus_session(self, task_id, started_at, minutes):
        """Ghi một phiên tập trung đã xong. Việc gắn với phiên đã bị xoá thì phiên vẫn được tính, chỉ không gắn với việc nào."""
        exists = task_id and self.conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
        self.conn.execute("INSERT INTO focus_sessions(task_id, started_at, minutes) VALUES(?, ?, ?)",
                          (task_id if exists else None, started_at, minutes))

    def focus_stats(self, now):
        """Số phiên và số phút tập trung hôm nay, số phút của từng ngày trong 7 ngày qua (ngày cuối là hôm nay)."""
        today = now.date()
        first = today - timedelta(days=6)
        rows = {row[0]: (row[1], row[2]) for row in self.conn.execute(
            "SELECT substr(started_at, 1, 10), COUNT(*), SUM(minutes) FROM focus_sessions WHERE started_at >= ? GROUP BY 1",
            (first.isoformat(),))}
        count, minutes = rows.get(today.isoformat(), (0, 0))
        days = [first + timedelta(days=offset) for offset in range(7)]
        return {"count": count, "minutes": minutes, "week": [(day, rows.get(day.isoformat(), (0, 0))[1]) for day in days]}

    # ---------- Checkpoint ----------

    def checkpoints(self, task_id):
        return self.conn.execute("SELECT * FROM checkpoints WHERE task_id=? ORDER BY position, id", (task_id,)).fetchall()

    def add_checkpoint(self, task_id, title):
        title = " ".join(title.split())
        if not title:
            return None
        return self.conn.execute(
            "INSERT INTO checkpoints(task_id, title, position) "
            "VALUES(?, ?, (SELECT COALESCE(MAX(position), -1) + 1 FROM checkpoints WHERE task_id=?))",
            (task_id, title, task_id)).lastrowid

    def set_checkpoint(self, checkpoint_id, done):
        self.conn.execute("UPDATE checkpoints SET done=? WHERE id=?", (int(done), checkpoint_id))

    def rename_checkpoint(self, checkpoint_id, title):
        title = " ".join(title.split())
        if title:
            self.conn.execute("UPDATE checkpoints SET title=? WHERE id=?", (title, checkpoint_id))

    def delete_checkpoint(self, checkpoint_id):
        self.conn.execute("DELETE FROM checkpoints WHERE id=?", (checkpoint_id,))

    # ---------- Truy vấn cho giao diện ----------

    def list_tasks(self, view, now, tag=0, search=""):
        day_end = (now.date() + timedelta(days=1)).isoformat()
        where, params = [], []
        if view == "today":
            where += ["t.done_at IS NULL", "t.due_at < ?"]
            params.append(day_end)
        elif view == "upcoming":
            where += ["t.done_at IS NULL", "t.due_at >= ?"]
            params.append(day_end)
        elif view == "all":
            where.append("t.done_at IS NULL")
        elif view == "done":
            where.append("t.done_at IS NOT NULL")
        elif view == "done_today":
            where += ["t.done_at >= ?", "t.done_at < ?"]
            params += [now.date().isoformat(), day_end]
        else:
            raise ValueError(view)
        if tag:
            where.append("t.id IN (SELECT task_id FROM task_tags WHERE tag_id = ?)")
            params.append(tag)
        if search:
            where.append("(t.title LIKE ? ESCAPE '\\' OR t.notes LIKE ? ESCAPE '\\')")
            pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params += [pattern, pattern]
        order = " ORDER BY t.done_at DESC, t.id DESC LIMIT 300" if view.startswith("done") else OPEN_ORDER
        return self.conn.execute(f"{TASK_SELECT} WHERE {' AND '.join(where)}{order}", params).fetchall()

    def calendar_tasks(self, first, last, tag=0):
        """Task chạm vào khoảng ngày [first, last), cộng việc lặp còn mở có thể rơi vào khoảng đó."""
        where = ("((t.due_at >= :first AND t.due_at < :last) OR (t.block_start >= :first AND t.block_start < :last) "
                 "OR (t.recur <> '' AND t.done_at IS NULL AND t.due_at < :last))")
        params = {"first": first.isoformat(), "last": last.isoformat(), "tag": tag}
        if tag:
            where += " AND t.id IN (SELECT task_id FROM task_tags WHERE tag_id = :tag)"
        return self.conn.execute(f"{TASK_SELECT} WHERE {where}", params).fetchall()

    def stats(self, now):
        today = now.date()
        day, next_day = today.isoformat(), (today + timedelta(days=1)).isoformat()
        row = self.conn.execute(
            """SELECT COALESCE(SUM(done_at IS NULL AND due_at >= :now AND due_at < :next), 0) AS today_open,
                      COALESCE(SUM(done_at IS NULL AND due_at < :now), 0)                     AS overdue,
                      COALESCE(SUM(done_at IS NULL AND due_at >= :day AND due_at < :next), 0) AS due_today,
                      COALESCE(SUM(done_at >= :day AND done_at < :next), 0)                   AS done_today,
                      COALESCE(SUM(done_at IS NULL AND due_at >= :next), 0)                   AS upcoming,
                      COALESCE(SUM(done_at IS NULL), 0)                                       AS open_total
               FROM tasks""",
            {"now": to_text(now), "day": day, "next": next_day}).fetchone()
        stats = dict(row)
        planned = stats["done_today"] + stats["due_today"]
        stats["planned"] = planned
        stats["rate"] = stats["done_today"] / planned if planned else None
        first = today - timedelta(days=6)
        counts = dict(self.conn.execute(
            "SELECT substr(done_at, 1, 10), COUNT(*) FROM tasks WHERE done_at >= ? GROUP BY 1",
            (first.isoformat(),)).fetchall())
        days = [first + timedelta(days=offset) for offset in range(7)]
        stats["week"] = [(item, counts.get(item.isoformat(), 0)) for item in days]
        return stats

    def blocks_today(self, now):
        day, next_day = now.date().isoformat(), (now.date() + timedelta(days=1)).isoformat()
        return self.conn.execute(
            TASK_SELECT + " WHERE t.done_at IS NULL AND t.block_start >= ? AND t.block_start < ? "
            "AND t.block_minutes > 0 ORDER BY t.block_start", (day, next_day)).fetchall()

    def nearest_deadline(self, now):
        return self.conn.execute(TASK_SELECT + " WHERE t.done_at IS NULL AND t.due_at > ? ORDER BY t.due_at LIMIT 1", (to_text(now),)).fetchone()

    # ---------- Dành cho agent ----------

    def scheduled_tasks(self):
        return self.conn.execute(TASK_SELECT + " WHERE t.done_at IS NULL AND (t.due_at IS NOT NULL "
                                 "OR t.block_start IS NOT NULL OR t.snooze_until IS NOT NULL)").fetchall()

    def sent_keys(self):
        return {tuple(row) for row in self.conn.execute("SELECT task_id, kind, stamp FROM sent_reminders")}

    def mark_sent(self, events):
        rows = [(task["id"], kind, stamp) for task, kind, stamp in events]
        if rows:
            with self.conn:
                self.conn.execute("BEGIN IMMEDIATE")
                self.conn.executemany("INSERT OR IGNORE INTO sent_reminders(task_id, kind, stamp) VALUES(?, ?, ?)", rows)

    def summary_tasks(self, now):
        """(việc quá hạn, việc còn lại hôm nay), hai danh sách không trùng nhau."""
        tasks = self.list_tasks("today", now)
        cutoff = to_text(now)
        overdue = [task for task in tasks if task["due_at"] < cutoff]
        return overdue, [task for task in tasks if task["due_at"] >= cutoff]

    def maintenance(self, today_text):
        """Dọn dẹp mỗi ngày một lần: bỏ lịch sử nhắc thừa và sao lưu xoay vòng 7 bản."""
        self.conn.execute("DELETE FROM sent_reminders WHERE task_id IN (SELECT id FROM tasks WHERE done_at IS NOT NULL)")
        self._backup_to(f"todo-{today_text}.db")
        folder = self._backup_folder()
        daily = sorted(name for name in os.listdir(folder) if name.startswith("todo-"))
        for name in daily[:-BACKUP_KEEP]:
            os.remove(os.path.join(folder, name))
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
