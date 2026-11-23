"""wait_for_main must outlast a ~25 s battle; the entry minimap poll must settle before retreating."""
import time
import combat

class IO:
    def __init__(self, main_after):
        self.n = 0; self.main_after = main_after
    def capture(self):
        self.n += 1
        return 1 if self.n >= self.main_after else 0

combat.time.sleep = lambda s: None
combat.is_main = lambda f: f == 1            # main screen returns after main_after frames (250 = 25 s at 0.1 s)
logs = []
assert combat.wait_for_main(IO(250), logs.append) is True, 'must wait past the old 100-frame limit'
assert combat.wait_for_main(IO(10**9), logs.append) is False and '600' in logs[-1]
assert combat.wait_for_main(IO(250), logs.append, max_frames=100) is False   # old behaviour still reachable
print('OK')
