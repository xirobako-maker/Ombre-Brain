"""
========================================
tools/dream/__init__.py — dream 工具入口
========================================

dream 是「我做一次梦——读最近 N 小时内有变动的所有桶，自己沉进去想
一遍」。这里把整个流程拆成三步：
1. candidates.py：筛选窗口内的桶 + 软上限
2. hints.py：连接提示 + 结晶提示
3. output.py：拼最终文本（近期活跃/active plan/feel 历史/
   连接提示/结晶提示）

dispatch() 整理普通经历；独立自我认知模块已移除。

对外暴露：dispatch(window_hours) → str
========================================
"""

from typing import Optional

from .. import _runtime as rt
from .candidates import collect_candidates
from .hints import build_connection_hint, build_crystal_hint
from ombrebrain.policy.surfacing import is_identity_record
from .output import format_dream_output


async def dispatch(
    window_hours: Optional[int] = 48,
) -> str:
    await rt.decay_engine.ensure_started()

    try:
        all_buckets = await rt.bucket_mgr.list_all(include_archive=False)
    except Exception as e:
        rt.logger.error(f"Dream failed to list buckets: {e}")
        return "记忆系统暂时无法访问。"

    all_buckets = [b for b in all_buckets if not is_identity_record(b)]
    window_hours = max(1, min(int(window_hours or 48), 24 * 14))
    recent = collect_candidates(all_buckets, window_hours)
    if not recent:
        return f"过去 {window_hours} 小时内没有需要整理的新记忆。"

    connection_hint = await build_connection_hint(recent)
    crystal_hint = await build_crystal_hint(all_buckets)

    final_text = await format_dream_output(
        recent=recent,
        all_buckets=all_buckets,
        window_hours=window_hours,
        connection_hint=connection_hint,
        crystal_hint=crystal_hint,
    )

    # them 追加在末尾，独立通道，不进融合打分（rule.md 13.3）。
    # dream 无 query，走的是按衰减权重取前三那条路：常被提起的人自然排在前面。
    # 关着 them 时返回空串，输出与没有这个模块时逐字一致。
    them_service = getattr(rt, "them_service", None)
    if them_service is not None:
        try:
            them_block = await them_service.surface()
        except Exception as exc:
            rt.logger.warning(f"them surface skipped / them 追加块跳过: {exc}")
        else:
            if them_block:
                final_text = f"{final_text}\n\n{them_block}"

    if rt.fire_webhook:
        await rt.fire_webhook("dream", {"recent": len(recent), "chars": len(final_text)})
    return final_text
