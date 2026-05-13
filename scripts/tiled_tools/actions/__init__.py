# -*- coding: utf-8 -*-
"""actions 子包：导入即注册。

新增 action 时，请在这里 import，让其装饰器副作用生效。
"""

from . import io_load        # noqa: F401
from . import io_save        # noqa: F401
from . import canvas_square  # noqa: F401
from . import rotate         # noqa: F401
from . import scale          # noqa: F401
from . import topdown_to_iso  # noqa: F401
from . import iso_to_topdown  # noqa: F401
from . import split_3x3      # noqa: F401
from . import save_all       # noqa: F401
from . import for_each       # noqa: F401
from . import pack_sheet     # noqa: F401
from . import build_tsx_sheet  # noqa: F401
from . import tile_repeat    # noqa: F401
