import os
import shutil
import subprocess
import sys


# Pre-build wheels. These need to be in sync with installer.cfg. Not the
# best way to do it, but let's not do things too fancy until we need them.
WHEEL_NEEDED = [
    'Kivy-Garden==0.1.4',
    'pycparser==2.18',
]
wheels_dir = os.path.join(os.path.dirname(__file__), 'build', 'wheels')
os.makedirs(wheels_dir, exist_ok=True)
for req in WHEEL_NEEDED:
    subprocess.check_call(
        [sys.executable, '-m', 'pip', 'wheel', req],
        cwd=wheels_dir,
    )


# Copy needed DLLs.
share_target = os.path.join(os.path.dirname(__file__), 'build', 'share')
if not os.path.isdir(share_target):
    shutil.copytree(os.path.join(sys.prefix, 'share'), share_target)

# Run pynsist to build the installer.
subprocess.check_call([sys.executable, '-m', 'nsist', 'installer.cfg'])
