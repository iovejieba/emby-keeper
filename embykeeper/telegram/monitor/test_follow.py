from .follow import FollowMonitor

__ignore__ = True


class TestFollowMonitor(FollowMonitor):
    name = "全部群组从众 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
    chat_follow_user = 3
    allow_same_user = True
