import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from screentl import utils
from screentl.storage import atomic_write_json, list_screenshots, next_screenshot_number


class ScreenshotStorageTests(unittest.TestCase):
    def test_recovers_sequence_from_existing_files_when_counter_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'screenshot_2_20260801_120000.png').touch()
            (folder / 'screenshot_8.png').touch()
            (folder / 'num.json').write_text('{broken', encoding='utf-8')

            self.assertEqual(next_screenshot_number(folder), 9)

    def test_respects_counter_when_it_is_ahead_of_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'screenshot_2_20260801_120000.png').touch()
            (folder / 'num.json').write_text('{"num": 12}', encoding='utf-8')

            self.assertEqual(next_screenshot_number(folder), 12)

    def test_sorts_duplicate_sequences_by_timestamp_then_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            names = [
                'screenshot_10_20260801_120010.png',
                'screenshot_2_20260801_120002.png',
                'screenshot_10_20260801_120001.png',
                'screenshot_10.png',
                'ignore.png',
            ]
            for name in names:
                (folder / name).touch()

            self.assertEqual(
                [path.name for path in list_screenshots(folder)],
                [
                    'screenshot_2_20260801_120002.png',
                    'screenshot_10.png',
                    'screenshot_10_20260801_120001.png',
                    'screenshot_10_20260801_120010.png',
                ],
            )

    def test_atomic_write_json_replaces_content_without_leaving_temp_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            destination = folder / 'num.json'
            destination.write_text('{"num": 1}', encoding='utf-8')

            atomic_write_json(destination, {'num': 4})

            self.assertEqual(json.loads(destination.read_text(encoding='utf-8')), {'num': 4})
            self.assertEqual(list(folder.glob('.num.json.*.tmp')), [])

    def test_screenshot_is_committed_before_counter_update(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)

            def write_screenshot(path):
                Path(path).write_bytes(b'png')

            with patch.object(utils.pyautogui, 'screenshot', side_effect=write_screenshot):
                screenshot_path = utils._do_screenshot(folder)

            self.assertTrue(screenshot_path.is_file())
            self.assertEqual(json.loads((folder / 'num.json').read_text(encoding='utf-8')), {'num': 1})
            self.assertEqual(list(folder.glob('.*.tmp.png')), [])

    def test_failed_screenshot_cleans_temporary_file_and_counter(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)

            def fail_after_write(path):
                Path(path).write_bytes(b'partial')
                raise RuntimeError('capture failed')

            with (
                patch.object(utils.pyautogui, 'screenshot', side_effect=fail_after_write),
                self.assertRaisesRegex(RuntimeError, 'capture failed'),
            ):
                utils._do_screenshot(folder)

            self.assertEqual(list(folder.glob('screenshot_*.png')), [])
            self.assertEqual(list(folder.glob('.*.tmp.png')), [])
            self.assertFalse((folder / 'num.json').exists())


if __name__ == '__main__':
    unittest.main()
