import asyncio
import logging

from loguru import logger

from embykeeper.log import formatter
from embykeeper.config import config

logger = logger.bind(scheme="telegram", nonotify=True)

stream_log = None
stream_msg = None
handler_log_id = None
handler_msg_id = None
change_handle_telegram = None
change_handle_notifier = None


async def _stop_notifier():
    global stream_log, stream_msg, handler_log_id, handler_msg_id

    if handler_log_id is not None:
        logger.remove(handler_log_id)
        handler_log_id = None
    if handler_msg_id is not None:
        logger.remove(handler_msg_id)
        handler_msg_id = None

    if stream_log:
        stream_log.close()
        await stream_log.join()
        stream_log = None
    if stream_msg:
        stream_msg.close()
        await stream_msg.join()
        stream_msg = None


def _handle_config_change(*args):
    async def _async():
        global stream_log, stream_msg

        await _stop_notifier()
        if config.notifier and config.notifier.enabled:
            streams = await start_notifier()
            if streams:
                stream_log, stream_msg = streams

    logger.debug("正在刷新 Telegram 消息通知.")
    asyncio.create_task(_async())


async def start_notifier():
    """消息通知初始化函数."""
    global stream_log, stream_msg, handler_log_id, handler_msg_id, change_handle_telegram, change_handle_notifier

    def _filter_log(record):
        notify = record.get("extra", {}).get("log", None)
        nonotify = record.get("extra", {}).get("nonotify", None)
        if (not nonotify) and (notify or record["level"].no == logging.ERROR):
            return True
        else:
            return False

    def _filter_msg(record):
        notify = record.get("extra", {}).get("msg", None)
        nonotify = record.get("extra", {}).get("nonotify", None)
        if (not nonotify) and notify:
            return True
        else:
            return False

    def _formatter(record):
        return "{level}#" + formatter(record)

    accounts = config.telegram.account
    notifier = config.notifier
    if notifier:
        account = None
        if notifier.enabled:
            if isinstance(notifier.account, int):
                try:
                    account = accounts[notifier.account - 1]
                except IndexError:
                    notifier = None
            elif isinstance(notifier, str):
                for a in accounts:
                    if a.phone == notifier:
                        account = a
                        break

    if account:
        from .session import ClientsSession
        from .log import TelegramStream

        async with ClientsSession([account]) as clients:
            async for a, tg in clients:
                logger.info(f'计划任务的关键消息将通过 Embykeeper Bot 发送至 "{account.phone}" 账号.')
                break
            else:
                logger.error(f'无法连接到 "{account.phone}" 账号, 无法发送日志推送.')
                return None

        stream_log = TelegramStream(
            account=account,
            instant=config.notifier.immediately,
        )
        handler_log_id = logger.add(
            stream_log,
            format=_formatter,
            filter=_filter_log,
        )
        stream_msg = TelegramStream(
            account=account,
            instant=True,
        )
        handler_msg_id = logger.add(
            stream_msg,
            format=_formatter,
            filter=_filter_msg,
        )
        if not change_handle_telegram:
            change_handle_telegram = config.on_change("telegram.account", _handle_config_change)
        if not change_handle_notifier:
            change_handle_notifier = config.on_change("notifier", _handle_config_change)
        return stream_log, stream_msg
    else:
        if not change_handle_notifier:
            change_handle_notifier = config.on_change("notifier", _handle_config_change)
        return None
