"""Find the Windows PC on the LAN and its Gato link/agent ports."""
import socket
import subprocess
import concurrent.futures as cf

NET = '192.168.0.'
PORTS = (8787, 8788, 8789, 8791, 8000, 4011, 3389, 445, 135)


subprocess.run(['arp', '-an'], capture_output=True)


def ping(i):
    r = subprocess.run(['ping', '-c1', '-W', '300', f'{NET}{i}'], capture_output=True)
    return i, r.returncode == 0


alive = []
with cf.ThreadPoolExecutor(max_workers=64) as ex:
    for i, ok in ex.map(ping, range(1, 255)):
        if ok:
            alive.append(i)
print('alive', [f'{NET}{i}' for i in alive])


def probe(args):
    i, p = args
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect((f'{NET}{i}', p))
        return f'{NET}{i}:{p}'
    except OSError:
        return None
    finally:
        s.close()


hits = []
with cf.ThreadPoolExecutor(max_workers=96) as ex:
    for r in ex.map(probe, [(i, p) for i in alive for p in PORTS]):
        if r:
            hits.append(r)
print('open', hits)
