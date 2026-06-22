import json
import os
from datetime import datetime
from typing import Any

from nonebot.log import logger
from nonebot_plugin_localstore import get_plugin_data_file


STATE_FILE = get_plugin_data_file("scheduled_tasks.json")
STATE_VERSION = 1


def _serialize_task(group_id: int, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
    result = {"group_id": group_id, "task_id": task_id, **data}
    if isinstance(result.get("time"), datetime):
        result["time"] = result["time"].isoformat()
    return result


def save_state() -> None:
    from .lottery import lotteries
    from .registration import registrations

    data = {
        "version": STATE_VERSION,
        "lotteries": [
            _serialize_task(group_id, lid, ldata)
            for group_id, group_lotteries in lotteries.items()
            for lid, ldata in group_lotteries.items()
        ],
        "registrations": [
            _serialize_task(group_id, rid, rdata)
            for group_id, group_registrations in registrations.items()
            for rid, rdata in group_registrations.items()
        ],
    }
    temp_file = STATE_FILE.with_suffix(f"{STATE_FILE.suffix}.tmp")
    try:
        temp_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_file, STATE_FILE)
    except Exception as e:
        logger.opt(exception=e).error("保存定时抽奖/报名状态失败")


def _load_task(
    item: Any,
    required_fields: set[str],
) -> tuple[int, str, dict[str, Any]] | None:
    if not isinstance(item, dict):
        return None
    try:
        group_id = int(item["group_id"])
        task_id = str(item["task_id"])
        task_time = datetime.fromisoformat(str(item["time"]))
    except (KeyError, TypeError, ValueError):
        return None

    data = {
        key: value
        for key, value in item.items()
        if key not in {"group_id", "task_id"}
    }
    data["time"] = task_time
    data["participants"] = (
        data["participants"] if isinstance(data.get("participants"), dict) else {}
    )
    if not required_fields.issubset(data):
        return None
    if "limit" in required_fields:
        try:
            data["limit"] = int(data["limit"])
        except (TypeError, ValueError):
            return None
        data["setter"] = str(data["setter"])
    return group_id, task_id, data


def load_state() -> None:
    from .lottery import lotteries
    from .registration import registrations

    if not STATE_FILE.exists():
        return
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.opt(exception=e).error("读取定时抽奖/报名状态失败，将忽略持久化文件")
        return
    if not isinstance(data, dict):
        logger.error("定时抽奖/报名持久化文件格式错误，将忽略该文件")
        return

    lotteries.clear()
    registrations.clear()
    skipped = 0

    raw_lotteries = data.get("lotteries", [])
    if not isinstance(raw_lotteries, list):
        raw_lotteries = []
        skipped += 1
    for item in raw_lotteries:
        loaded = _load_task(item, {"name", "time", "participants"})
        if loaded is None:
            skipped += 1
            continue
        group_id, lid, ldata = loaded
        lotteries[group_id][lid] = ldata

    raw_registrations = data.get("registrations", [])
    if not isinstance(raw_registrations, list):
        raw_registrations = []
        skipped += 1
    for item in raw_registrations:
        loaded = _load_task(
            item,
            {"name", "setter", "time", "limit", "participants"},
        )
        if loaded is None:
            skipped += 1
            continue
        group_id, rid, rdata = loaded
        registrations[group_id][rid] = rdata

    logger.info(
        f"已恢复 {sum(map(len, lotteries.values()))} 个定时抽奖和 "
        f"{sum(map(len, registrations.values()))} 个定时报名"
    )
    if skipped:
        logger.warning(f"持久化文件中有 {skipped} 条无效任务，已跳过")


async def restore_scheduled_tasks(bot, scheduler) -> None:
    from .lottery import execute_lottery, lotteries
    from .registration import close_registration, registrations

    if scheduler is None:
        return

    now = datetime.now()
    bot_id = str(bot.self_id)

    for group_id, group_lotteries in list(lotteries.items()):
        for lid, ldata in list(group_lotteries.items()):
            if str(ldata.get("bot_id") or bot_id) != bot_id:
                continue
            job_id = str(ldata.get("job_id") or f"lottery_{lid}")
            ldata["job_id"] = job_id
            if ldata["time"] <= now:
                await execute_lottery(bot, group_id, lid)
            else:
                scheduler.add_job(
                    execute_lottery,
                    "date",
                    run_date=ldata["time"],
                    args=(bot, group_id, lid),
                    id=job_id,
                    replace_existing=True,
                )

    for group_id, group_registrations in list(registrations.items()):
        for rid, rdata in list(group_registrations.items()):
            if str(rdata.get("bot_id") or bot_id) != bot_id:
                continue
            job_id = str(rdata.get("job_id") or f"registration_{rid}")
            rdata["job_id"] = job_id
            if rdata["time"] <= now:
                await close_registration(bot, group_id, rid)
            else:
                scheduler.add_job(
                    close_registration,
                    "date",
                    run_date=rdata["time"],
                    args=(bot, group_id, rid),
                    id=job_id,
                    replace_existing=True,
                )

    save_state()
