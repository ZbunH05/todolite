"""Đồng hồ Pomodoro: tập trung 25 phút, nghỉ ngắn 5 phút, xong 4 phiên thì nghỉ dài 15 phút.

Trạng thái nằm trong bảng settings nên giao diện, agent và đồng hồ nổi cùng thấy một đồng hồ, và đóng
cửa sổ thì đồng hồ vẫn chạy. Agent là nơi chuyển phiên: nó thức đúng lúc hết phiên, ghi phiên vừa xong
rồi báo. Mỗi lần đổi trạng thái là một giao dịch BEGIN IMMEDIATE đọc lại trạng thái đang lưu, nên hai
tiến trình cùng bấm, hay cùng thấy hết phiên, cũng không ghi đè hay đếm trùng một phiên.

Các hàm thuần (started, paused, finished...) nhận và trả về State, không đụng database, nên test được dễ.
"""
from collections import namedtuple
from datetime import timedelta

from .schedule import from_text, to_text_seconds

FOCUS, SHORT, LONG = "focus", "short", "long"
PHASES = (FOCUS, SHORT, LONG)
PHASE_NAMES = {FOCUS: "Tập trung", SHORT: "Nghỉ ngắn", LONG: "Nghỉ dài"}
# Khoá cài đặt: (mặc định, nhỏ nhất, lớn nhất, bước khi bấm - +)
LENGTHS = {"pomo_focus": (25, 5, 120, 5), "pomo_short": (5, 1, 30, 1), "pomo_long": (15, 5, 60, 5), "pomo_rounds": (4, 2, 8, 1)}
PHASE_KEYS = {FOCUS: "pomo_focus", SHORT: "pomo_short", LONG: "pomo_long"}
CHAIN_LIMIT = timedelta(minutes=2)  # thức dậy trễ hơn thế này (máy ngủ) thì phiên sau tính từ lúc thức, không từ lúc lẽ ra hết phiên

State = namedtuple("State", "phase end left round task_id")  # end: datetime khi đang chạy, left: số giây còn lại khi tạm dừng
Config = namedtuple("Config", "focus short long rounds auto_break auto_focus")
Session = namedtuple("Session", "task_id start minutes")


def setting_number(store, key):
    default, low, high, _step = LENGTHS[key]
    try:
        return min(max(int(store.setting(key)), low), high)
    except ValueError:
        return default


def config(store):
    return Config(*(setting_number(store, key) for key in ("pomo_focus", "pomo_short", "pomo_long", "pomo_rounds")),
                  store.setting("pomo_auto_break") == "1", store.setting("pomo_auto_focus") == "1")


def read(store):
    phase, end, left, task = (store.setting(key) for key in ("pomo_phase", "pomo_end", "pomo_left", "pomo_task"))
    return State(phase if phase in PHASES else FOCUS, from_text(end) if end else None, int(left) if left else None,
                 int(store.setting("pomo_round") or 0), int(task) if task else None)


def _save(store, state):
    store.set_setting("pomo_phase", state.phase)
    store.set_setting("pomo_end", to_text_seconds(state.end) if state.end else "")
    store.set_setting("pomo_left", state.left if state.left is not None else "")
    store.set_setting("pomo_round", state.round)
    store.set_setting("pomo_task", state.task_id or "")


def minutes_of(cfg, phase):
    return {FOCUS: cfg.focus, SHORT: cfg.short, LONG: cfg.long}[phase]


def running(state):
    return state.end is not None


def seconds_left(state, cfg, now):
    """Số giây còn lại của phiên đang hiện, dù đang chạy, tạm dừng hay chờ bấm Bắt đầu."""
    if state.end is not None:
        return max((state.end - now).total_seconds(), 0)
    return state.left if state.left is not None else minutes_of(cfg, state.phase) * 60


# ---------- Hàm thuần ----------

def started(state, cfg, now):
    return state._replace(end=now + timedelta(seconds=seconds_left(state, cfg, now)), left=None)


def paused(state, now):
    return state._replace(end=None, left=max(round((state.end - now).total_seconds()), 1))


def skipped(state):
    """Bỏ qua phiên đang hiện, không ghi gì: bỏ phiên tập trung thì sang nghỉ ngắn, bỏ giờ nghỉ thì sang tập trung."""
    if state.phase == FOCUS:
        return State(SHORT, None, None, state.round, state.task_id)
    return State(FOCUS, None, None, 0 if state.phase == LONG else state.round, state.task_id)


def reset(state):
    return State(FOCUS, None, None, 0, state.task_id)


def chosen(state, phase):
    return state._replace(phase=phase, end=None, left=None)


def finished(state, cfg, now):
    """Phiên đang chạy vừa hết: (trạng thái mới, phiên tập trung cần ghi hoặc None).

    Xong phiên tập trung thì sang nghỉ ngắn, đủ số phiên của một vòng thì nghỉ dài. Phiên sau tự chạy nếu cài đặt cho phép,
    tính nối tiếp từ lúc phiên trước lẽ ra kết thúc để đồng hồ không trôi dần theo độ trễ của timer.
    """
    if state.phase == FOCUS:
        done = state.round + 1
        session = Session(state.task_id, state.end - timedelta(minutes=cfg.focus), cfg.focus)
        phase, auto, count = (LONG if done % cfg.rounds == 0 else SHORT), cfg.auto_break, done
    else:
        session = None
        phase, auto, count = FOCUS, cfg.auto_focus, 0 if state.phase == LONG else state.round
    if not auto:
        return State(phase, None, None, count, state.task_id), session
    start = state.end if now - state.end <= CHAIN_LIMIT else now
    return State(phase, start + timedelta(minutes=minutes_of(cfg, phase)), None, count, state.task_id), session


def notice(old, new, cfg, title=""):
    """(tiêu đề, dòng) của thông báo chuyển phiên."""
    if old.phase == FOCUS:
        head = f"Xong phiên tập trung {new.round}/{cfg.rounds}" if new.phase == SHORT else f"Xong cả {cfg.rounds} phiên tập trung"
        if title:
            head += f": {title}"
        rest = f"{PHASE_NAMES[new.phase]} {minutes_of(cfg, new.phase)} phút"
        return head, f"{rest} đã bắt đầu, đứng dậy vươn vai nhé" if running(new) else f"Bấm Bắt đầu để {rest.lower()}"
    if running(new):
        return "Hết giờ nghỉ", f"Phiên tập trung {cfg.focus} phút đã bắt đầu"
    return "Hết giờ nghỉ", "Sẵn sàng cho phiên tập trung tiếp theo"


# ---------- Thao tác trên database ----------

def change(store, step, *args):
    """Một thao tác của người dùng: đọc lại trạng thái mới nhất trong giao dịch, đổi, ghi. Trả về trạng thái mới."""
    with store.conn:
        store.conn.execute("BEGIN IMMEDIATE")
        state = step(read(store), *args)
        _save(store, state)
    return state


def start(store, now):
    return change(store, lambda state: state if running(state) else started(state, config(store), now))


def pause(store, now):
    return change(store, lambda state: paused(state, now) if running(state) else state)


def skip(store):
    return change(store, skipped)


def stop(store):
    return change(store, reset)


def choose(store, phase):
    return change(store, chosen, phase)


def link(store, task_id):
    return change(store, lambda state: state._replace(task_id=task_id))


def complete_due(store, now):
    """Chuyển phiên nếu phiên đang chạy đã hết. Trả về (tiêu đề, dòng) của thông báo, hoặc None. Gọi lặp lại vô hại."""
    with store.conn:
        store.conn.execute("BEGIN IMMEDIATE")
        state = read(store)
        if state.end is None or state.end > now:
            return None
        cfg = config(store)
        new, session = finished(state, cfg, now)
        if session:
            store.add_focus_session(session.task_id, to_text_seconds(session.start), session.minutes)
        task = store.get_task(state.task_id) if state.task_id else None
        message = notice(state, new, cfg, task["title"] if task and state.phase == FOCUS else "")
        _save(store, new)
        store.set_setting("pomo_notice", "|".join((to_text_seconds(state.end), *message)))
    return message
