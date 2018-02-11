#!python3.6

import os
import sys

ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT, 'pkgs'))
sys.path.append(ROOT)

if __name__ == '__main__':
    import main
    main.MyApp().run()
