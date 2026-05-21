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
from . import iso45_tile_spec  # noqa: F401
from . import iso_to_topdown  # noqa: F401

from . import split_3x3      # noqa: F401
from . import split_connected  # noqa: F401
from . import save_all       # noqa: F401
from . import for_each       # noqa: F401
from . import pack_sheet     # noqa: F401
from . import build_tsx_sheet  # noqa: F401
from . import tile_repeat    # noqa: F401
from . import gen_default_masks  # noqa: F401
from . import load_dir      # noqa: F401
from . import mask_blend_set  # noqa: F401
from . import multi_terrain_wang_set  # noqa: F401
from . import make_seamless  # noqa: F401
from . import wang_2edge_compose_map  # noqa: F401
from . import brush_remap_tsx  # noqa: F401
from . import remap_tmj_gids  # noqa: F401
from . import tileset_to_iso45_matrix  # noqa: F401





