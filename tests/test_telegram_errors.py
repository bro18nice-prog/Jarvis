"""Network errors quote the full API address; the bot token must never reach logs or chats."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import telegram_remote

TOKEN = '123456:TEST-token-not-real-0000000000000000'


class TokenMaskingTests(unittest.TestCase):
    def remote(self, log):
        with patch.object(telegram_remote, '_env', return_value={'TELEGRAM_TOKEN': TOKEN}):
            return telegram_remote.Remote(log, lambda text: '', lambda: '')

    def test_token_is_masked_in_error_text(self):
        r = self.remote(lambda line: None)
        err = Exception(f'Max retries exceeded with url: /bot{TOKEN}/sendMessage')
        self.assertNotIn(TOKEN, r._err(err))
        self.assertIn('***', r._err(err))

    def test_failed_send_does_not_log_the_token(self):
        lines = []
        r = self.remote(lines.append)
        with patch.object(r, '_call', side_effect=Exception(f'url: /bot{TOKEN}/sendMessage')):
            r.send('1', 'salut')
        self.assertTrue(lines)
        self.assertFalse(any(TOKEN in line for line in lines))


if __name__ == '__main__':
    unittest.main()
