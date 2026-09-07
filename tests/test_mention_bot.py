import unittest

from mention_bot import DirectSlackGateway, is_target_mention, normalize_messages


class FakeClient:
    def conversations_history(self, **kwargs):
        return {
            "messages": [
                {"user": "U1", "text": "채널 메시지", "ts": "10.0"}
            ]
        }


class MentionTests(unittest.TestCase):
    def test_target_user_mention_triggers(self):
        event = {
            "user": "UOTHER",
            "text": "<@UME> 결과 확인 부탁드립니다.",
            "ts": "20.0",
        }
        self.assertTrue(is_target_mention(event, "UME"))

    def test_own_and_bot_messages_do_not_trigger(self):
        own = {"user": "UME", "text": "<@UME> 메모", "ts": "20.0"}
        bot = {
            "user": "UBOT",
            "bot_id": "B1",
            "text": "<@UME> 알림",
            "ts": "20.0",
        }
        self.assertFalse(is_target_mention(own, "UME"))
        self.assertFalse(is_target_mention(bot, "UME"))

    def test_normalize_messages_drops_bot_and_sorts(self):
        rows = [
            {"user": "U2", "text": "나중", "ts": "2.0"},
            {"user": "UBOT", "bot_id": "B1", "text": "봇", "ts": "1.5"},
            {"user": "U1", "text": "먼저", "ts": "1.0"},
        ]
        self.assertEqual(
            [message["ts"] for message in normalize_messages(rows)],
            ["1.0", "2.0"],
        )


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_includes_thread_trigger_event(self):
        trigger = {
            "user": "U2",
            "text": "<@UME> 스레드에서 확인 부탁드립니다.",
            "ts": "20.0",
            "thread_ts": "10.0",
        }
        gateway = DirectSlackGateway(FakeClient(), trigger_event=trigger)
        messages = await gateway.recent("C1")
        self.assertEqual([message["ts"] for message in messages], ["10.0", "20.0"])


if __name__ == "__main__":
    unittest.main()
