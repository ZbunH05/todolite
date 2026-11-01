import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta

from todolite import db
from todolite.db import SCHEMA_VERSION, Store, tag_key, task_tag_names
from todolite.schedule import to_text

NOW = datetime(2026, 10, 31, 10, 0)  # Thứ Bảy


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = os.path.join(self.folder.name, "data", "todo.db")
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()


class Tasks(StoreCase):
    def test_add_uses_default_reminders(self):
        task = self.store.get_task(self.store.add_task("  Mua   sữa  "))
        self.assertEqual((task["title"], task["remind"], task["cp_total"]), ("Mua sữa", "30,15", 0))

    def test_empty_title_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add_task("   ")

    def test_update_rejects_unknown_column(self):
        task_id = self.store.add_task("A")
        with self.assertRaises(ValueError):
            self.store.update_task(task_id, done_at="x")

    def test_sql_injection_in_title_is_stored_literally(self):
        title = "x'); DROP TABLE tasks; --"
        task_id = self.store.add_task(title)
        self.assertEqual(self.store.get_task(task_id)["title"], title)

    def test_delete_cascades(self):
        task_id = self.store.add_task("A", due_at="2026-10-31 09:00")
        self.store.add_checkpoint(task_id, "c")
        self.store.mark_sent([(self.store.get_task(task_id), "due", "x")])
        self.store.delete_task(task_id)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0], 0)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM sent_reminders").fetchone()[0], 0)

    def test_complete_is_idempotent(self):
        task_id = self.store.add_task("A")
        self.store.complete_task(task_id, NOW)
        first = self.store.get_task(task_id)["done_at"]
        self.store.complete_task(task_id, NOW + timedelta(hours=1))
        self.assertEqual(self.store.get_task(task_id)["done_at"], first)

    def test_schema_version_is_recorded(self):
        self.assertEqual(self.store.conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def test_newer_database_is_refused(self):
        self.store.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
        with self.assertRaises(RuntimeError):
            Store(self.path)
        self.store.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


class Recurring(StoreCase):
    def make(self, **fields):
        return self.store.add_task("Lặp", recur="daily", due_at="2026-10-31 09:00", **fields)

    def test_completing_spawns_next_with_fresh_checkpoints(self):
        task_id = self.make(priority=3, tags=["Học tập"])
        checkpoint = self.store.add_checkpoint(task_id, "bước 1")
        self.store.set_checkpoint(checkpoint, True)
        new_id = self.store.complete_task(task_id, NOW)
        new = self.store.get_task(new_id)
        self.assertEqual((new["due_at"], new["priority"], task_tag_names(new), new["recur"]),
                         ("2026-11-01 09:00", 3, ["Học tập"], "daily"))
        self.assertEqual([row["done"] for row in self.store.checkpoints(new_id)], [0])
        self.assertEqual((new["cp_total"], new["cp_done"]), (1, 0))

    def test_block_moves_with_the_deadline(self):
        task_id = self.make(block_start="2026-10-31 08:00", block_minutes=45)
        new = self.store.get_task(self.store.complete_task(task_id, NOW))
        self.assertEqual((new["block_start"], new["block_minutes"]), ("2026-11-01 08:00", 45))

    def test_reopen_removes_spawned_task(self):
        task_id = self.make()
        new_id = self.store.complete_task(task_id, NOW)
        self.store.reopen_task(task_id)
        self.assertIsNone(self.store.get_task(new_id))
        self.assertIsNone(self.store.get_task(task_id)["done_at"])

    def test_monthly_keeps_anchor_day(self):
        task_id = self.store.add_task("Tiền nhà", recur="monthly", due_at="2027-01-31 09:00")
        self.assertEqual(self.store.get_task(task_id)["recur"], "monthly:31")
        february = self.store.complete_task(task_id, datetime(2027, 1, 31, 10))
        self.assertEqual(self.store.get_task(february)["due_at"], "2027-02-28 09:00")
        march = self.store.complete_task(february, datetime(2027, 2, 28, 10))
        self.assertEqual(self.store.get_task(march)["due_at"], "2027-03-31 09:00")

    def test_changing_due_updates_monthly_anchor(self):
        task_id = self.store.add_task("Tiền nhà", recur="monthly", due_at="2027-01-31 09:00")
        self.store.update_task(task_id, due_at="2027-01-10 09:00")
        self.assertEqual(self.store.get_task(task_id)["recur"], "monthly:10")

    def test_recurring_without_due_date(self):
        task_id = self.store.add_task("Lặp", recur="daily")
        new = self.store.get_task(self.store.complete_task(task_id, NOW))
        self.assertEqual(new["due_at"], "2026-11-01 10:00")


class Blocks(StoreCase):
    def test_start_keeps_seconds_for_accurate_countdown(self):
        task_id = self.store.add_task("A")
        self.store.start_block(task_id, 25, datetime(2026, 10, 31, 10, 0, 40))
        self.assertEqual(self.store.get_task(task_id)["block_start"], "2026-10-31 10:00:40")

    def test_extend_running_block(self):
        task_id = self.store.add_task("A")
        self.store.start_block(task_id, 25, NOW)
        self.store.extend_block(task_id, 5, NOW + timedelta(minutes=10))
        self.assertEqual(self.store.get_task(task_id)["block_minutes"], 30)

    def test_extend_finished_block_continues_from_now(self):
        task_id = self.store.add_task("A")
        self.store.start_block(task_id, 25, NOW)
        self.store.extend_block(task_id, 10, NOW + timedelta(minutes=40))
        self.assertEqual(self.store.get_task(task_id)["block_minutes"], 50)

    def test_end(self):
        task_id = self.store.add_task("A")
        self.store.start_block(task_id, 25, NOW)
        self.store.end_block(task_id)
        self.assertIsNone(self.store.get_task(task_id)["block_start"])


class Checkpoints(StoreCase):
    def test_order_and_counts(self):
        task_id = self.store.add_task("A")
        ids = [self.store.add_checkpoint(task_id, name) for name in ("một", "hai", "ba")]
        self.store.set_checkpoint(ids[1], True)
        self.assertEqual([row["title"] for row in self.store.checkpoints(task_id)], ["một", "hai", "ba"])
        task = self.store.get_task(task_id)
        self.assertEqual((task["cp_done"], task["cp_total"]), (1, 3))

    def test_blank_is_ignored(self):
        task_id = self.store.add_task("A")
        self.assertIsNone(self.store.add_checkpoint(task_id, "   "))

    def test_rename_and_delete(self):
        task_id = self.store.add_task("A")
        checkpoint = self.store.add_checkpoint(task_id, "cũ")
        self.store.rename_checkpoint(checkpoint, "mới")
        self.assertEqual(self.store.checkpoints(task_id)[0]["title"], "mới")
        self.store.delete_checkpoint(checkpoint)
        self.assertEqual(self.store.checkpoints(task_id), [])


class Views(StoreCase):
    def setUp(self):
        super().setUp()
        add = self.store.add_task
        self.old = add("Cũ", due_at="2026-10-30 09:00")
        self.passed = add("Sáng nay", due_at="2026-10-31 08:00")
        self.later = add("Chiều nay", due_at="2026-10-31 15:00", tags=["Công việc"])
        self.all_day = add("Cả ngày", due_at="2026-10-31 23:59", all_day=1)
        self.tomorrow = add("Mai", due_at="2026-11-01 09:00")
        self.undated = add("Không hạn", notes="100% ghi_chú")
        self.done = add("Đã xong", due_at="2026-10-31 09:00")
        self.store.complete_task(self.done, NOW)

    def ids(self, view, **filters):
        return [row["id"] for row in self.store.list_tasks(view, NOW, **filters)]

    def test_today_contains_overdue_and_today_in_order(self):
        self.assertEqual(self.ids("today"), [self.old, self.passed, self.later, self.all_day])

    def test_upcoming(self):
        self.assertEqual(self.ids("upcoming"), [self.tomorrow])

    def test_all_puts_undated_last(self):
        self.assertEqual(self.ids("all")[-1], self.undated)
        self.assertNotIn(self.done, self.ids("all"))

    def test_done(self):
        self.assertEqual(self.ids("done"), [self.done])

    def test_filters(self):
        self.assertEqual(self.ids("all", tag=self.store.find_tag("công việc")["id"]), [self.later])
        self.assertEqual(self.ids("all", search="sáng"), [self.passed])

    def test_search_treats_wildcards_literally(self):
        self.assertEqual(self.ids("all", search="100%"), [self.undated])
        self.assertEqual(self.ids("all", search="ghi_chú"), [self.undated])
        self.assertEqual(self.ids("all", search="%"), [self.undated])

    def test_stats_cards_do_not_overlap(self):
        stats = self.store.stats(NOW)
        self.assertEqual((stats["today_open"], stats["overdue"]), (2, 2))
        self.assertEqual((stats["done_today"], stats["due_today"], stats["planned"]), (1, 3, 4))
        self.assertEqual(stats["rate"], 0.25)
        self.assertEqual(stats["upcoming"], 1)

    def test_all_day_task_turns_overdue_only_after_the_day(self):
        self.assertEqual(self.store.stats(datetime(2026, 11, 1, 0, 1))["overdue"], 4)

    def test_week_series(self):
        week = self.store.stats(NOW)["week"]
        self.assertEqual(len(week), 7)
        self.assertEqual((to_text(datetime(*week[-1][0].timetuple()[:3]))[:10], week[-1][1]), ("2026-10-31", 1))

    def test_rate_is_none_without_plans(self):
        self.store.conn.execute("DELETE FROM tasks")
        self.assertIsNone(self.store.stats(NOW)["rate"])

    def test_summary_lists_do_not_overlap(self):
        overdue, today = self.store.summary_tasks(NOW)
        self.assertEqual([row["id"] for row in overdue], [self.old, self.passed])
        self.assertEqual([row["id"] for row in today], [self.later, self.all_day])

    def test_nearest_deadline_skips_all_day_and_past(self):
        self.assertEqual(self.store.nearest_deadline(NOW)["id"], self.later)


class Tags(StoreCase):
    def test_presets_exist_on_a_new_database(self):
        self.assertEqual([row["name"] for row in self.store.tags()][:3], ["Công việc", "Học tập", "Gia đình"])

    def test_key_ignores_marks_case_and_separators(self):
        for spelling in ("Sức khoẻ", "sức khỏe", "SUC-KHOE", "suc_khoe", "  sức   khoẻ "):
            self.assertEqual(tag_key(spelling), "suc khoe")
        self.assertEqual(tag_key("Đọc sách"), "doc sach")

    def test_spelling_variants_do_not_create_duplicates(self):
        before = len(self.store.tags())
        task_id = self.store.add_task("A", tags=["hoc-tap", "#Học Tập", "HỌC TẬP"])
        self.assertEqual(len(self.store.tags()), before)
        self.assertEqual(task_tag_names(self.store.get_task(task_id)), ["Học tập"])

    def test_new_tag_gets_display_name_and_a_color(self):
        task_id = self.store.add_task("A", tags=["dự-án-lớn"])
        row = self.store.find_tag("dự án lớn")
        self.assertEqual(row["name"], "Dự án lớn")
        self.assertRegex(row["color"], "^#[0-9A-F]{6}$")
        self.assertEqual(task_tag_names(self.store.get_task(task_id)), ["Dự án lớn"])

    def test_several_tags_follow_tag_order(self):
        task_id = self.store.add_task("A", tags=["gia đình", "công việc"])
        self.assertEqual(task_tag_names(self.store.get_task(task_id)), ["Công việc", "Gia đình"])

    def test_set_task_tags_replaces(self):
        task_id = self.store.add_task("A", tags=["công việc"])
        self.store.set_task_tags(task_id, ["học tập", "cá nhân"])
        self.assertEqual(task_tag_names(self.store.get_task(task_id)), ["Học tập", "Cá nhân"])
        self.store.set_task_tags(task_id, [])
        self.assertEqual(task_tag_names(self.store.get_task(task_id)), [])

    def test_counts_only_open_tasks(self):
        kept = self.store.add_task("A", tags=["công việc"])
        finished = self.store.add_task("B", tags=["công việc"])
        self.store.complete_task(finished, NOW)
        self.assertEqual(self.store.find_tag("công việc")["id"], self.store.tags()[0]["id"])
        self.assertEqual(self.store.tags()[0]["n"], 1)
        self.assertIsNotNone(self.store.get_task(kept))

    def test_rename(self):
        tag_id = self.store.find_tag("gia đình")["id"]
        self.assertTrue(self.store.rename_tag(tag_id, "Nhà  mình"))
        self.assertEqual(self.store.find_tag("nha minh")["name"], "Nhà mình")

    def test_rename_refuses_clash_and_blank(self):
        tag_id = self.store.find_tag("gia đình")["id"]
        self.assertFalse(self.store.rename_tag(tag_id, "cong viec"))
        self.assertFalse(self.store.rename_tag(tag_id, "   "))
        self.assertEqual(self.store.find_tag("gia đình")["id"], tag_id)

    def test_delete_keeps_tasks(self):
        task_id = self.store.add_task("A", tags=["gia đình"])
        self.store.delete_tag(self.store.find_tag("gia đình")["id"])
        self.assertEqual(task_tag_names(self.store.get_task(task_id)), [])

    def test_deleting_task_cleans_links(self):
        task_id = self.store.add_task("A", tags=["gia đình"])
        self.store.delete_task(task_id)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM task_tags").fetchone()[0], 0)

    def test_tag_label(self):
        self.assertEqual(self.store.tag_label("hoc-tap"), "Học tập")
        self.assertEqual(self.store.tag_label("chưa-có"), "Chưa có")


class Migration(unittest.TestCase):
    """Nâng cấp từ dữ liệu thật của phiên bản 1."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = os.path.join(self.folder.name, "todo.db")
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        db._create_schema(conn)
        add = "INSERT INTO tasks(title, tag, due_at, created_at, recur) VALUES(?, ?, ?, '2026-10-01 08:00', ?)"
        conn.execute(add, ("Báo cáo", "công-việc", "2026-10-31 09:00", ""))
        conn.execute(add, ("Tập gym", "sức-khoẻ", "2026-10-31 18:00", "weekly"))
        conn.execute(add, ("Dự án riêng", "dự-án-lớn", None, ""))
        conn.execute(add, ("Không nhãn", "", None, ""))
        conn.execute("INSERT INTO checkpoints(task_id, title) VALUES(1, 'bước 1')")
        conn.execute("INSERT INTO settings VALUES('summary_time', '06:45')")
        conn.execute("PRAGMA user_version=1")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.folder.cleanup()

    def test_data_survives_and_tags_move_over(self):
        store = Store(self.path)
        self.assertEqual(store.conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        rows = {row["title"]: row for row in store.list_tasks("all", NOW)}
        self.assertEqual(len(rows), 4)
        self.assertEqual(task_tag_names(rows["Báo cáo"]), ["Công việc"])
        self.assertEqual(task_tag_names(rows["Tập gym"]), ["Sức khoẻ"])
        self.assertEqual(task_tag_names(rows["Dự án riêng"]), ["Dự án lớn"])
        self.assertEqual(task_tag_names(rows["Không nhãn"]), [])
        self.assertEqual(rows["Báo cáo"]["cp_total"], 1)
        self.assertEqual(rows["Tập gym"]["recur"], "weekly")
        self.assertEqual(store.setting("summary_time"), "06:45")
        store.close()

    def test_old_column_is_gone(self):
        store = Store(self.path)
        columns = [row["name"] for row in store.conn.execute("PRAGMA table_info(tasks)")]
        self.assertNotIn("tag", columns)
        store.close()

    def test_backup_is_taken_before_upgrading(self):
        Store(self.path).close()
        backup = os.path.join(self.folder.name, "backups", f"before-schema-{SCHEMA_VERSION}.db")
        conn = sqlite3.connect(backup)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks WHERE tag<>''").fetchone()[0], 3)
        conn.close()

    def test_second_open_does_nothing(self):
        Store(self.path).close()
        store = Store(self.path)
        self.assertEqual(len(store.tags()), 7)
        store.close()

    def test_failed_upgrade_leaves_old_data_intact(self):
        original = db.MIGRATIONS

        def broken(conn):
            db._add_tags(conn)
            raise RuntimeError("giữa chừng")

        db.MIGRATIONS = (original[0], broken)
        try:
            with self.assertRaises(RuntimeError):
                Store(self.path)
        finally:
            db.MIGRATIONS = original
        conn = sqlite3.connect(self.path)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks WHERE tag<>''").fetchone()[0], 3)
        conn.close()


class Calendar(StoreCase):
    def test_range_is_half_open(self):
        inside = self.store.add_task("Trong", due_at="2026-11-01 00:00")
        self.store.add_task("Ngoài", due_at="2026-11-08 00:00")
        rows = self.store.calendar_tasks(date(2026, 11, 1), date(2026, 11, 8))
        self.assertEqual([row["id"] for row in rows], [inside])

    def test_block_only_task_is_included(self):
        task_id = self.store.add_task("Khối", block_start="2026-11-02 09:00", block_minutes=30)
        self.assertEqual([row["id"] for row in self.store.calendar_tasks(date(2026, 11, 1), date(2026, 11, 8))], [task_id])

    def test_done_tasks_stay_visible(self):
        task_id = self.store.add_task("Xong", due_at="2026-11-02 09:00")
        self.store.complete_task(task_id, NOW)
        self.assertEqual(len(self.store.calendar_tasks(date(2026, 11, 1), date(2026, 11, 8))), 1)

    def test_older_recurring_task_is_included_for_projection(self):
        self.store.add_task("Lặp", due_at="2026-01-05 09:00", recur="weekly")
        self.assertEqual(len(self.store.calendar_tasks(date(2026, 11, 1), date(2026, 11, 8))), 1)

    def test_tag_filter(self):
        wanted = self.store.add_task("A", due_at="2026-11-02 09:00", tags=["gia đình"])
        self.store.add_task("B", due_at="2026-11-02 10:00", tags=["công việc"])
        tag_id = self.store.find_tag("gia đình")["id"]
        rows = self.store.calendar_tasks(date(2026, 11, 1), date(2026, 11, 8), tag_id)
        self.assertEqual([row["id"] for row in rows], [wanted])

    def test_block_carries_the_deadline_inside_it(self):
        task_id = self.store.add_task("A", due_at="2026-11-02 09:30", block_start="2026-11-02 09:00", block_minutes=60)
        self.store.snooze(task_id, 10)
        self.store.move_on_calendar(task_id, "block", timedelta(days=2, hours=1))
        row = self.store.get_task(task_id)
        self.assertEqual((row["due_at"], row["block_start"], row["snooze_until"]), ("2026-11-04 10:30", "2026-11-04 10:00", None))

    def test_block_leaves_a_later_deadline_alone(self):
        task_id = self.store.add_task("A", due_at="2026-11-06 17:00", block_start="2026-11-02 09:00", block_minutes=60)
        self.store.move_on_calendar(task_id, "block", timedelta(days=1))
        row = self.store.get_task(task_id)
        self.assertEqual((row["due_at"], row["block_start"]), ("2026-11-06 17:00", "2026-11-03 09:00"))

    def test_deadline_leaves_a_separate_block_alone(self):
        task_id = self.store.add_task("A", due_at="2026-11-06 17:00", block_start="2026-11-02 09:00", block_minutes=60)
        self.store.move_on_calendar(task_id, "due", timedelta(days=1))
        row = self.store.get_task(task_id)
        self.assertEqual((row["due_at"], row["block_start"]), ("2026-11-07 17:00", "2026-11-02 09:00"))

    def test_all_day_task_moves_by_day(self):
        task_id = self.store.add_task("A", due_at="2026-11-02 23:59", all_day=1)
        self.store.move_on_calendar(task_id, "due", timedelta(days=3))
        row = self.store.get_task(task_id)
        self.assertEqual((row["due_at"], row["all_day"]), ("2026-11-05 23:59", 1))

    def test_moving_monthly_task_updates_anchor(self):
        task_id = self.store.add_task("A", due_at="2026-11-02 10:00", recur="monthly")
        self.store.move_on_calendar(task_id, "due", timedelta(days=3))
        self.assertEqual(self.store.get_task(task_id)["recur"], "monthly:5")


class Settings(StoreCase):
    def test_defaults_and_overrides(self):
        self.assertEqual(self.store.setting("theme"), "dark")
        self.store.set_setting("theme", "dark")
        self.store.set_setting("theme", "light")
        self.assertEqual(self.store.setting("theme"), "light")

    def test_secret_is_encrypted_at_rest(self):
        self.store.set_secret("telegram_token", "123456:ABC-mã-bí-mật")
        self.assertEqual(self.store.secret("telegram_token"), "123456:ABC-mã-bí-mật")
        stored = self.store.setting("telegram_token")
        self.assertNotIn("123456", stored)
        self.assertNotIn("ABC", stored)

    def test_empty_secret_stays_empty(self):
        self.store.set_secret("telegram_token", "abc")
        self.store.set_secret("telegram_token", "")
        self.assertEqual(self.store.setting("telegram_token"), "")
        self.assertEqual(self.store.secret("telegram_token"), "")

    def test_ui_request_is_consumed_once(self):
        self.store.set_setting("ui_request", "task:5")
        self.assertEqual(self.store.take_ui_request(), "task:5")
        self.assertEqual(self.store.take_ui_request(), "")


class TwoProcesses(StoreCase):
    def test_data_version_changes_only_for_other_connections(self):
        other = Store(self.path)
        before = self.store.data_version()
        self.store.add_task("mình tự ghi")
        self.assertEqual(self.store.data_version(), before)
        other.add_task("tiến trình khác ghi")
        self.assertNotEqual(self.store.data_version(), before)
        other.close()

    def test_reader_is_not_blocked_while_writer_holds_transaction(self):
        other = Store(self.path)
        self.store.add_task("A")
        other.conn.execute("BEGIN IMMEDIATE")
        other.conn.execute("INSERT INTO settings VALUES('window', 'x')")
        self.assertEqual(len(self.store.list_tasks("all", NOW)), 1)
        other.conn.execute("ROLLBACK")
        other.close()


class Maintenance(StoreCase):
    def test_backup_rotates_and_is_readable(self):
        self.store.add_task("A")
        for day in range(1, 10):
            self.store.maintenance(f"2026-10-{day:02d}")
        folder = os.path.join(os.path.dirname(self.path), "backups")
        names = sorted(os.listdir(folder))
        self.assertEqual(len(names), 7)
        self.assertEqual(names[-1], "todo-2026-10-09.db")
        self.assertTrue(all(name.startswith("todo-") for name in names))
        copy = sqlite3.connect(os.path.join(folder, names[-1]))
        self.assertEqual(copy.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
        copy.close()

    def test_rotation_leaves_upgrade_backup_alone(self):
        folder = os.path.join(os.path.dirname(self.path), "backups")
        os.makedirs(folder, exist_ok=True)
        keeper = os.path.join(folder, "before-schema-2.db")
        open(keeper, "wb").close()
        for day in range(1, 10):
            self.store.maintenance(f"2026-10-{day:02d}")
        self.assertTrue(os.path.exists(keeper))

    def test_sent_history_of_finished_tasks_is_purged(self):
        task_id = self.store.add_task("A", due_at="2026-10-31 09:00")
        self.store.mark_sent([(self.store.get_task(task_id), "due", "x")])
        self.store.complete_task(task_id, NOW)
        self.store.maintenance("2026-10-31")
        self.assertEqual(self.store.sent_keys(), set())


if __name__ == "__main__":
    unittest.main()
