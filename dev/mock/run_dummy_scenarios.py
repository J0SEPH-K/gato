import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mock_loop as m

# Scenario A: nothing ever answers the click -> must keep clicking, then skip the spot at ~15 s (old code stopped at ~6 s)
b, hands, notes, alive = m.run_scenario("A", 18, [[520, 340]])
skipped = any("건너뛰" in n[1] for n in notes)
stopped = any("정지" in n[1] and "더미" in n[1] for n in notes)
print("A: skip after >=15 s:", skipped, "| stopped by dummy rule:", stopped)

# Scenario B: fight starts after 9 s -> no stop, counter restarts
t0 = time.time()
sc = lambda: {"scene": "battle" if 9 < time.time() - t0 < 13 else "main", "triggers": []}
b, hands, notes, alive = m.run_scenario("B", 20, [[520, 340]], sc)
stopped = any("정지" in n[1] and "더미" in n[1] for n in notes)
print("B: stopped by dummy rule:", stopped)

# Scenario C (seen live at 15:35): 14 s of unanswered clicks + skip must not trip the 30 s no-fight stop
b, hands, notes, alive = m.run_scenario("C", 38, [[520, 340]])
early_stop = [n for n in notes if "팅 의심" in n[1] and n[0] - notes[0][0] < 40.0]
print("C: 30 s no-fight stop before the skip window ended:", bool(early_stop))
sys.exit(1 if (not skipped or stopped or early_stop) else 0)
