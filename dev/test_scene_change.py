"""HO-11: post-battle scene-change must not false-stop; notify_img must be the image sender (MOCKED-ONLY)."""
import os, sys, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'mock')); sys.path.insert(0, os.path.dirname(HERE))
import mac_stub
import numpy as np, cv2
import brain, vision as vis

base = cv2.imread(os.path.join(HERE, 'mock', 'main_scene.png'))
noise = np.random.RandomState(1).randint(0, 255, base.shape, dtype=np.uint8)
shifted = cv2.warpAffine(base, np.float32([[1, 0, 300], [0, 1, 120]]), (base.shape[1], base.shape[0]))

def mk(ignore=False):
    b = brain.Brain.__new__(brain.Brain)
    b._prev_main = base[:vis.FIELD_H].copy(); b._shutdown_at = None; b._stop_reason = ''
    b.ignore_teleport = ignore; b.notes = []; b.imgs = []
    b._log = b.notes.append; b._notify_img = lambda m, i: b.imgs.append(m)
    return b

def run(frames, ignore=False):
    b = mk(ignore)
    for f in frames:
        b._grab_main = lambda normalize=True, f=f: f.copy()
        b._check_scene_change()
    return b

def sim(f): return vis.scene_similarity(base[:vis.FIELD_H], f[:vis.FIELD_H])

fails = 0
def check(name, ok):
    global fails; fails += 0 if ok else 1; print(('PASS ' if ok else 'FAIL ') + name)

# a post-battle return: same map, camera moved -> soft-low similarity, never a stop
print('shifted sim', round(sim(shifted), 3), 'noise sim', round(sim(noise), 3))
b = run([shifted] * 5)
check('soft-low post-battle frames x5 -> no stop', b._shutdown_at is None)
# hard change twice (map move / GM summon) -> stop for a normal mob
b = run([noise, noise])
check('hard change on 2 consecutive checks -> stop', b._shutdown_at is not None and '배경' in b._stop_reason)
b = run([noise, base, noise])
check('hard change not consecutive -> no stop', b._shutdown_at is None)
b = run([noise, noise], ignore=True)
check('ignore_teleport mob -> never stops', b._shutdown_at is None)
# binding
src = open(os.path.join(os.path.dirname(HERE), 'prism.py')).read()
check('prism notify_img bound to notifier.image', 'notify_img=self.notifier.image,' in src and 'notify_img=self.notifier.text' not in src)
import inspect, notify
check('Notifier.image accepts (msg, img)', list(inspect.signature(notify.Notifier.image).parameters)[1:3] == ['msg', 'img_bgr'])
sys.exit(1 if fails else 0)
