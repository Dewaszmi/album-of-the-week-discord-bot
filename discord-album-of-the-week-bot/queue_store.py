import json
import os


class QueueStore:
    def __init__(self, path: str):
        self.path = path
        self.main = []
        self.bonus = []
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                self.main = data.get("main", [])
                self.bonus = data.get("bonus", [])
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({"main": self.main, "bonus": self.bonus}, f, indent=4)

    def get(self, name: str) -> list:
        if name == "main":
            return self.main
        if name == "bonus":
            return self.bonus
        raise ValueError(f"Unknown queue: {name}")
