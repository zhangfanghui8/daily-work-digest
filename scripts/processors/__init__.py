"""L2 规则层：归并 raw 数据、生成 digest。"""

from .merge import merge_daily, merge_week

__all__ = ["merge_daily", "merge_week"]
