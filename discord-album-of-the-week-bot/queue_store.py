import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone


class QueueStore:
    def __init__(self, path: str):
        self.path = path
        self.main: list = []
        self.bonus: list = []
        self.backlog: list = []
        self._ensure_file()
        self.reload()

    def _ensure_file(self):
        if not os.path.exists(self.path):
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._write_file({"main": [], "bonus": [], "backlog": []})

    def _read_file(self) -> dict:
        if not os.path.exists(self.path):
            return {"main": [], "bonus": [], "backlog": []}

        with open(self.path, "r") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                if os.path.getsize(self.path) == 0:
                    return {"main": [], "bonus": [], "backlog": []}
                return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {"main": [], "bonus": [], "backlog": []}
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _write_file(self, data: dict):
        directory = os.path.dirname(self.path) or "."
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def reload(self):
        data = self._read_file()
        self._replace_list(self.main, data.get("main", []))
        self._replace_list(self.bonus, data.get("bonus", []))
        self._replace_list(self.backlog, data.get("backlog", []))

    @staticmethod
    def _replace_list(target: list, source: list):
        target.clear()
        target.extend(source)

    def save(self):
        self._write_file(
            {"main": self.main, "bonus": self.bonus, "backlog": self.backlog}
        )

    def get_queue(self, name: str) -> list:
        if name == "main":
            return self.main
        if name == "bonus":
            return self.bonus
        raise ValueError(f"Unknown queue: {name}")

    def reorder(self, queue_name: str, order: list[int]):
        queue = self.get_queue(queue_name)
        if len(order) != len(queue):
            raise ValueError("Order length does not match queue length")
        if sorted(order) != list(range(len(queue))):
            raise ValueError("Order must be a permutation of queue indices")
        reordered = [queue[i] for i in order]
        self._replace_list(queue, reordered)
        self.save()

    def remove_at(self, queue_name: str, index: int) -> dict:
        queue = self.get_queue(queue_name)
        if index < 0 or index >= len(queue):
            raise IndexError("Index out of range")
        removed = queue.pop(index)
        self.save()
        return removed

    def add_backlog_note(self, text: str, added_by: str = "") -> dict:
        note = {
            "text": text.strip(),
            "added_by": added_by.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.backlog.append(note)
        self.save()
        return note

    def update_backlog_note(self, index: int, text: str) -> dict:
        if index < 0 or index >= len(self.backlog):
            raise IndexError("Index out of range")
        self.backlog[index]["text"] = text.strip()
        self.save()
        return self.backlog[index]

    def remove_backlog_note(self, index: int) -> dict:
        if index < 0 or index >= len(self.backlog):
            raise IndexError("Index out of range")
        removed = self.backlog.pop(index)
        self.save()
        return removed

    def append_album(self, queue_name: str, entry: dict) -> dict:
        queue = self.get_queue(queue_name)
        queue.append(entry)
        self.save()
        return entry
