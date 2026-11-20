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

# Scenario D (client report: crowded map, many players on the mobs): several mobs are unreachable
# in a row. The macro must never stop for that - it skips, then clears the skipped spots and keeps
# clicking until a countdown actually starts.
b, hands, notes, alive = m.run_scenario("D", 120, [[300, 300], [520, 340], [700, 400], [420, 480]])
d_stop = [n for n in notes if "정지" in n[1]]
d_skips = [n for n in notes if "건너뛰" in n[1]]
d_reset = [n for n in notes if "전체 해제" in n[1]]
print("D: skips:", len(d_skips), "| full resets:", len(d_reset), "| stopped:", len(d_stop))

# Scenario E: crowded map, then the countdown finally starts -> must fight, no stop anywhere
t0 = time.time()
sc = lambda: {"scene": "battle" if time.time() - t0 > 60 else "main", "triggers": []}
b, hands, notes, alive = m.run_scenario("E", 75, [[300, 300], [520, 340], [700, 400], [420, 480]], sc)
e_stop = [n for n in notes if "정지" in n[1]]
e_fight = alive and any("전투 진입" in n[1] or "전투화면" in n[1] for n in notes)
print("E: fought:", bool(e_fight), "| stopped:", len(e_stop))

bad = (not skipped or stopped or early_stop or d_stop or not d_reset or e_stop)
print("all passed" if not bad else "FAILED")
sys.exit(1 if bad else 0)
