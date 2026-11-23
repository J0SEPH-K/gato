"""'포만감 템 없음' must not fire from sprite pixels while the gauge is healthy."""
import numpy as np
import vision as vis

def frame(food_px=None, fire=True):
    f = np.full((768, 1024, 3), 90, np.uint8)
    if fire:
        f[426, 573] = f[426, 574] = (230, 230, 230)          # sum 690 x2 = the trigger signature
    # gauge frame: black line above the fill, dark right border, green fill of food_px pixels
    f[669, 150] = (0, 0, 0)
    f[vis.FOOD_BAR_Y, vis.FOOD_BAR_X[1] + 1] = (0, 0, 0)
    n = 0 if food_px is None else food_px
    for x in range(vis.FOOD_BAR_X[0], vis.FOOD_BAR_X[0] + n):
        f[vis.FOOD_BAR_Y, x] = (42, 133, 84)
    return f

W = vis.FOOD_BAR_X[1] - vis.FOOD_BAR_X[0] + 1
assert '포만감 템 없음' not in vis.check_triggers(frame(int(W * 0.97))), 'healthy gauge must veto'
assert '포만감 템 없음' in vis.check_triggers(frame(int(W * 0.05))), 'low gauge must still fire'
g = frame(int(W * 0.5)); g[669, 150] = (71, 211, 162)        # gauge not readable (covered)
assert '포만감 템 없음' in vis.check_triggers(g), 'unreadable gauge keeps the trigger'
assert '포만감 템 없음' not in vis.check_triggers(frame(int(W * 0.97), fire=False))
print('OK')
