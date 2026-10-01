"""Offline checks; desktop actions and network calls are mocked."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import quick
from voice import clean_for_speech


class QuickCommandsTests(unittest.TestCase):
    def test_romanian_volume_command(self):
        with patch('hands.control_media') as action:
            reply, rest = quick.handle('Dă mai încet!')
        action.assert_called_once_with('volum_jos', 6)
        self.assertTrue(reply)
        self.assertEqual(rest, '')

    def test_local_command_then_unhandled_request(self):
        with patch('hands.control_media') as action:
            reply, rest = quick.handle('pauza si explica gravitatia')
        action.assert_called_once_with('play_pauza', 1)
        self.assertTrue(reply)
        self.assertEqual(rest, 'explica gravitatia')

    def test_does_not_execute_later_commands_after_unknown_request(self):
        with patch('hands.control_media') as action:
            self.assertEqual(quick.handle('explica gravitatia si pauza'),
                             (None, 'explica gravitatia si pauza'))
        action.assert_not_called()

    def test_missing_application_is_left_for_conversation(self):
        with patch('hands.deschide_aplicatie', return_value='Nu am gasit aplicatia.'):
            self.assertEqual(quick.handle('deschide aplicatia-inexistenta'),
                             (None, 'deschide aplicatia-inexistenta'))


class SpeechTextTests(unittest.TestCase):
    def test_removes_code_and_replaces_links(self):
        self.assertEqual(clean_for_speech('**Salut** ```secret = 1``` https://example.com'),
                         'Salut linkul')

    def test_preserves_decimal_comma(self):
        self.assertEqual(clean_for_speech('Costa 3,5 lei, azi.'), 'Costa 3,5 lei azi.')

    def test_english_name_is_not_rewritten(self):
        self.assertEqual(clean_for_speech('Jarvis', 'en'), 'Jarvis')


if __name__ == '__main__':
    unittest.main()
