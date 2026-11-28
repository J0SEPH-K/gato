"""Checks the auto-updater without the internet: version compare, asset pick, size/hash gate,
frozen-only guard, and that apply() writes a detached installer script.
    python dev/mock/run_update_test.py"""
import hashlib, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import config
config.BASE_DIR = tempfile.mkdtemp(prefix='gato_upd_')
config.RES_DIR = config.BASE_DIR
import update

fails = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond: fails.append(name)

open(os.path.join(config.RES_DIR, 'VERSION'), 'w').write('1.0.3\n')

check('1.0.4 is newer than 1.0.3', update._tag_key('v1.0.4') > update._tag_key('1.0.3'))
check('1.0.3 is not newer than 1.0.3', update._tag_key('v1.0.3') <= update._tag_key('1.0.3'))
check('1.0.10 is newer than 1.0.9', update._tag_key('v1.0.10') > update._tag_key('v1.0.9'))
check('a junk tag does not crash', update._tag_key('v') == (0, 0, 0))

BODY = b'INSTALLER-BYTES' * 1000
SHA = hashlib.sha256(BODY).hexdigest()

class R:
    """File-like: read(n) must run out at EOF, like a real HTTP body."""
    def __init__(self, data): self.data = data; self.i = 0
    def read(self, n=None):
        if n is None:
            out = self.data[self.i:]; self.i = len(self.data); return out
        out = self.data[self.i:self.i + n]; self.i += len(out); return out
    def __enter__(self): return self
    def __exit__(self, *a): return False

def rel(tag, digest=True, state='uploaded'):
    a = {'name': 'GatoSetup.exe', 'state': state, 'size': len(BODY),
         'browser_download_url': 'https://example.invalid/GatoSetup.exe'}
    if digest: a['digest'] = 'sha256:' + SHA
    return json.dumps({'tag_name': tag, 'assets': [a]}).encode()

def serve(release, asset=BODY):
    def fake(req, timeout=0):
        return R(asset if 'example.invalid' in getattr(req, 'full_url', '') else release)
    update.urllib.request.urlopen = fake

serve(rel('v1.0.4'))
info = update.check()
check('newer release is offered with its hash', info and info['tag'] == 'v1.0.4' and info['sha256'] == SHA, info)
p = update.download(info)
check('download writes the file', open(p, 'rb').read() == BODY and p.endswith('.exe'), p)

serve(rel('v1.0.3'))
check('same version -> no update', update.check() is None)
serve(rel('v1.0.2'))
check('older release -> no update', update.check() is None)
serve(rel('v1.0.9', state='starter'))
check('an asset still uploading is skipped', update.check() is None)

serve(rel('v1.0.5'), BODY + b'extra')
try:
    update.download(update.check()); check('wrong size is rejected', False)
except RuntimeError as e:
    check('wrong size is rejected', '\ud06c\uae30' in str(e), e)
serve(rel('v1.0.6', digest=False), BODY)
info6 = update.check(); info6['sha256'] = 'deadbeef' * 8
try:
    update.download(info6); check('wrong SHA256 is rejected', False)
except RuntimeError as e:
    check('wrong SHA256 is rejected', 'SHA256' in str(e), e)

logs = []
spawned = []
update.subprocess.Popen = lambda cmd, **kw: spawned.append((cmd, kw))
update.apply('/tmp/GatoSetup-x.exe', logs.append)
check('apply spawns the script detached', spawned and spawned[0][0][:2] == ['cmd', '/c'], spawned)
cmd = os.path.join(config.BASE_DIR, 'update', 'apply.cmd')
body = open(cmd, encoding='utf-8').read()
# The installer's [Run] section owns the relaunch, so apply.cmd installs and stops there.
check('apply writes a detached install-only script',
      '/VERYSILENT' in body and '/tmp/GatoSetup-x.exe' in body and 'start ""' not in body, body)

class Api:
    class vision:
        @staticmethod
        def note(k, m): pass
    class brain: running = False
    class engine: pass
    def __init__(self): self._update_ready = None
sys.frozen = True
check('install() runs in a frozen build', update.install(Api()) is not None)
del sys.frozen
check('install() does nothing in a source checkout', update.install(Api()) is None)
print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
