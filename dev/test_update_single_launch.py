"""After an update exactly ONE process may be launched, and the launcher is the installer.
The installer's [Run] section starts the app on a silent install, so the updater's
apply.cmd must install and NOT also `start` the exe.
    python dev/test_update_single_launch.py
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

fails = []


def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else ' -- ' + str(extra)))
    if not cond:
        fails.append(name)


# --- apply.cmd: install only, no relaunch -------------------------------------------
import config

config.BASE_DIR = tempfile.mkdtemp(prefix='gato_upd1_')
import update

spawned = []
update.subprocess.Popen = lambda cmd, **kw: spawned.append((cmd, kw))
update.apply(os.path.join(config.BASE_DIR, 'GatoSetup-v9.exe'), lambda m: None)
cmd_path = os.path.join(config.BASE_DIR, 'update', 'apply.cmd')
body = open(cmd_path, encoding='utf-8').read()
check('apply still spawns the detached script', spawned and spawned[0][0][:2] == ['cmd', '/c'], spawned)
check('the script still installs silently', '/VERYSILENT' in body, body)
check('the script does NOT start the exe itself', 'start ""' not in body, body)
check('the script still deletes itself', 'del "%~f0"' in body, body)

# --- installer: silent installs launch exactly once ---------------------------------
iss = open(os.path.join(ROOT, 'installer', 'gato.iss'), encoding='utf-8').read()
run_block = iss.split('[Run]', 1)[1].split('[Code]', 1)[0]
launches = [ln for ln in run_block.splitlines()
            if ln.strip().lower().startswith('filename:') and 'gato.exe' in ln.lower()]
check('the installer has Gato.exe launch entries', bool(launches), run_block)
# Inno's /VERYSILENT sets BOTH Silent and WizardSilent, so an entry gated only on
# `skipifsilent` never fires on an update and an entry gated on `WizardSilent` fires
# on both modes. What matters is the count per mode.
low = [ln.lower() for ln in launches]
silent_launches = [ln for ln, s in zip(launches, low) if 'wizardsilent' in s and 'skipifsilent' not in s]
interactive_launches = [ln for ln, s in zip(launches, low) if 'wizardsilent' not in s]
check('a SILENT install (the updater) launches exactly once', len(silent_launches) == 1, launches)
check('an INTERACTIVE install launches at most once (shortcut is the launch path)',
      len(interactive_launches) <= 1, launches)
check('no Gato.exe launch is fully unconditional (both modes at once)',
      all(('wizardsilent' in s) or ('skipifsilent' in s) for s in low),
      launches)
postinstall = [ln for ln in launches if 'postinstall' in ln.lower()]
check('at most one entry is a postinstall entry', len(postinstall) <= 1, postinstall)

# --- and the guard is wired into the entry point ------------------------------------
prism = open(os.path.join(ROOT, 'prism.py'), encoding='utf-8').read()
main_src = prism.split('def main():', 1)[1]
check('main() claims the single-instance mutex', 'claim_single_instance()' in main_src, main_src[:400])
check('main() exits when another instance won',
      re.search(r'if busy:\s*\n(\s*#[^\n]*\n)*\s*os\._exit\(0\)', main_src) is not None, main_src[:600])
check('the mutex is claimed before the API/window is built',
      main_src.index('claim_single_instance()') < main_src.index('api = Api()'), main_src[:400])
check('prism does not define the mutex helpers twice',
      prism.count('def _instance_mutex():') == 1 and prism.count('def claim_single_instance(') == 1,
      (prism.count('def _instance_mutex():'), prism.count('def claim_single_instance(')))

print('FAILED: %s' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
