import asyncio
from typing import Any

from nonebot.adapters.onebot.v11 import ActionFailed, Bot, Message, MessageSegment
from nonebot.log import logger

REMINDER_TEXT = "有人发起抽奖啦，亲爱的鼠粉，看看要不要参与一下哦！"

# QQ numbers are stored as strings so persisted and API-provided values compare reliably.
lottery_reminder_users: set[str] = set()


def set_lottery_reminder(user_id: int | str, enabled: bool) -> bool:
    user_id = str(user_id)
    changed = (
        user_id not in lottery_reminder_users
        if enabled
        else user_id in lottery_reminder_users
    )

    if enabled:
        lottery_reminder_users.add(user_id)
    else:
        lottery_reminder_users.discard(user_id)

    if changed:
        from .persistence import save_state

        save_state()
    return changed


def _member_user_ids(members: list[Any]) -> set[str]:
    user_ids = set()
    for member in members:
        if isinstance(member, dict):
            user_id = member.get("user_id")
        else:
            user_id = getattr(member, "user_id", None)
        if user_id is not None:
            user_ids.add(str(user_id))
    return user_ids


async def notify_lottery_reminder_users(bot: Bot, group_id: int) -> None:
    if not lottery_reminder_users:
        return

    await asyncio.sleep(1)

    try:
        members = await bot.get_group_member_list(group_id=group_id, no_cache=False)
        reminder_user_ids = lottery_reminder_users & _member_user_ids(members)
        if not reminder_user_ids:
            return

        segments = []
        for user_id in sorted(reminder_user_ids, key=int):
            segments.extend((MessageSegment.at(user_id), MessageSegment.text(" ")))
        segments.append(MessageSegment.text(REMINDER_TEXT))

        await bot.send_group_msg(group_id=group_id, message=Message(segments))
    except ActionFailed as e:
        logger.warning(f"群 {group_id} 发送抽奖提醒失败：{e}")
    except Exception as e:  # noqa: BLE001 - reminders must not fail lottery creation
        logger.opt(exception=e).error(f"群 {group_id} 获取成员列表或发送抽奖提醒失败")
