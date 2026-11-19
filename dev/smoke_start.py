"""Smoke test: start the real Brain headless against the running game, watch the log, stop.
Usage: .venv\\Scripts\\python dev\\smoke_start.py [seconds]   (game must be on the field)
"""
import sys, os, time, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT); sys.path.insert(0, ROOT)
import run_gato
run_gato._seed_settings()
import prism
api = prism.Api()
print('init ok; start_block_reason=', api.brain.start_block_reason())
lines = []
orig = api.vision.note
def note(kind, msg, *a, **k):
    lines.append('%s %s' % (time.strftime('%H:%M:%S'), msg))
    return orig(kind, msg, *a, **k)
api.vision.note = note
api.brain._log = lambda s: lines.append('%s %s' % (time.strftime('%H:%M:%S'), s))
t0 = time.time()
while api.brain.start_block_reason() and time.time()-t0 < 90: time.sleep(1)
print('ready after %.0fs reason=%r' % (time.time()-t0, api.brain.start_block_reason()))
r = api.start()
print('start() -> running=', r.get('running') if isinstance(r, dict) else r, 'running=', api.brain.running)
dur = int(sys.argv[1]) if len(sys.argv) > 1 else 40
time.sleep(dur)
try:
    print('status', json.dumps(api.status(), ensure_ascii=False, default=str)[:600])
except Exception as e:
    print('status err', e)
api.stop()
time.sleep(3)
print('running after stop=', api.brain.running)
print('--- log (%d lines, last 40) ---' % len(lines))
for l in lines[-40:]:
    print(l)
