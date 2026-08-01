import unittest

from screentl.instance_lock import (
    ERROR_ALREADY_EXISTS,
    SingleInstance,
    activate_existing_window,
)


class FakeWindowsApi:
    def __init__(self, handle=100, last_error=0, activated=True):
        self.handle = handle
        self.last_error = last_error
        self.activated = activated
        self.created_names = []
        self.closed_handles = []
        self.activated_titles = []

    def create_mutex(self, name):
        self.created_names.append(name)
        return self.handle, self.last_error

    def close_handle(self, handle):
        self.closed_handles.append(handle)

    def activate_window(self, title):
        self.activated_titles.append(title)
        return self.activated


class SingleInstanceTests(unittest.TestCase):
    def test_acquires_and_releases_first_instance(self):
        api = FakeWindowsApi()
        instance = SingleInstance('Local\\TestApp', api=api)

        self.assertTrue(instance.acquire())
        self.assertTrue(instance.acquire())
        instance.release()

        self.assertEqual(api.created_names, ['Local\\TestApp'])
        self.assertEqual(api.closed_handles, [100])

    def test_rejects_duplicate_instance_and_closes_duplicate_handle(self):
        api = FakeWindowsApi(last_error=ERROR_ALREADY_EXISTS)
        instance = SingleInstance('Local\\TestApp', api=api)

        self.assertFalse(instance.acquire())

        self.assertEqual(api.closed_handles, [100])

    def test_raises_when_mutex_creation_fails(self):
        api = FakeWindowsApi(handle=0, last_error=5)
        instance = SingleInstance('Local\\TestApp', api=api)

        with self.assertRaises(OSError):
            instance.acquire()

    def test_activation_is_delegated_to_platform_api(self):
        api = FakeWindowsApi(activated=True)

        self.assertTrue(activate_existing_window('Screenshot Time-lapse', api=api))
        self.assertEqual(api.activated_titles, ['Screenshot Time-lapse'])


if __name__ == '__main__':
    unittest.main()
