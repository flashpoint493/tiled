# -*- coding: utf-8 -*-
"""使 `python -m tiled_tools` 等价于 `python -m tiled_tools.cli`。"""

from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
