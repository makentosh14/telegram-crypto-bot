import json
import os

MEMORY_FILE = "signal_memory.json"

class SignalMemory:
    def __init__(self):
        self.memory = {}
        self.load_memory()

    def load_memory(self):
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r") as f:
                try:
                    self.memory = json.load(f)
                except json.JSONDecodeError:
                    self.memory = {}
        else:
            self.memory = {}

    def save_memory(self):
        with open(MEMORY_FILE, "w") as f:
            json.dump(self.memory, f, indent=2)

    def update_result(self, symbol, result):
        """
        result: 'win' or 'loss'
        """
        if symbol not in self.memory:
            self.memory[symbol] = {"wins": 0, "losses": 0}

        if result == "win":
            self.memory[symbol]["wins"] += 1
        elif result == "loss":
            self.memory[symbol]["losses"] += 1

        self.save_memory()

    def get_win_rate(self, symbol):
        if symbol not in self.memory:
            return 0.5  # Neutral default

        wins = self.memory[symbol]["wins"]
        losses = self.memory[symbol]["losses"]
        total = wins + losses

        if total == 0:
            return 0.5

        return wins / total

    def is_trusted_symbol(self, symbol, threshold=0.65, min_trades=5):
        """
        Returns True if the symbol has proven to be profitable historically.
        """
        if symbol not in self.memory:
            return False

        wins = self.memory[symbol]["wins"]
        losses = self.memory[symbol]["losses"]
        total = wins + losses

        if total < min_trades:
            return False

        win_rate = wins / total
        return win_rate >= threshold
