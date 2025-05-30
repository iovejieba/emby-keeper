import asyncio
from datetime import datetime, time

from ..lock import (
    pornfans_nohp,
    pornemby_messager_enabled,
    pornemby_messager_mids,
    pornemby_messager_mids_lock,
    pornemby_alert,
)
from . import Messager

__ignore__ = True


class PornembyMessager(Messager):
    name = "Pornemby"
    chat_name = "embytestflight"
    default_messages = ["pornemby-common-wl@latest.yaml * 100"]

    async def init(self):
        self.lock = asyncio.Lock()
        pornemby_messager_enabled[self.me.id] = True
        async with pornemby_messager_mids_lock:
            if self.me.id not in pornemby_messager_mids:
                pornemby_messager_mids[self.me.id] = []
        return True

    async def send(self, message):
        if pornemby_alert.get(self.me.id, False):
            self.log.info(f"由于风险急停取消发送.")
            return
        nohp_date = pornfans_nohp.get(self.me.id, None)
        if nohp_date and nohp_date >= datetime.today().date():
            self.log.info(f"取消发送: 血量已耗尽.")
            return
        msg = await super().send(message)
        if msg:
            pornemby_messager_mids[self.me.id].append(msg.id)
        return msg
