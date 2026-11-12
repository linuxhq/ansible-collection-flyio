# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import FlyioApiError
from ansible_collections.linuxhq.flyio.plugins.modules import apps
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


class AppsTests(TestCase):
    def test_rejects_nonpositive_delete_timeout(self):
        module = FakeModule({"delete_timeout": 0, "force": True, "name": "example"})

        with (
            patch.object(apps, "get_app") as get,
            self.assertRaises(ModuleFail) as raised,
        ):
            apps.ensure_absent(module, {})

        get.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "delete_timeout must be greater than zero",
        )

    def test_existing_app_is_unchanged(self):
        current = {"name": "example"}
        module = FakeModule({"name": "example", "org_slug": "linuxhq"})

        with (
            patch.object(apps, "get_app", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_creates_app_with_network(self):
        module = FakeModule({"name": "example", "network": "private", "org_slug": "linuxhq"})
        created = {"name": "example"}

        with (
            patch.object(apps, "get_app", side_effect=[None, created]),
            patch.object(apps, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps",
            {"name": "example", "network": "private", "org_slug": "linuxhq"},
        )
        self.assertEqual(raised.exception.values["app"], created)

    def test_deletes_app(self):
        current = {"name": "example"}
        module = FakeModule({"delete_timeout": 120, "force": True, "name": "example"})

        with (
            patch.object(apps, "get_app", return_value=current),
            patch.object(apps, "delete_result", return_value=None) as delete,
            patch.object(apps, "wait_for_app_absent", return_value=None) as wait,
            patch.object(apps, "wait_deadline", return_value=130),
            patch.object(apps, "seconds_left", return_value=100),
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_absent(module, {})

        delete.assert_called_once_with({}, "/apps/example", timeout=120)
        wait.assert_called_once_with({}, "example", 100)
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["app"], current)

    def test_app_deleted_elsewhere_after_read_is_unchanged(self):
        module = FakeModule({"delete_timeout": 120, "force": True, "name": "example"})

        with (
            patch.object(apps, "get_app", return_value={"name": "example"}),
            patch.object(apps, "delete_result", side_effect=FlyioApiError("gone", status_code=404)),
            patch.object(apps, "wait_for_app_absent") as wait,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_absent(module, {})

        wait.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["message"], "App already absent")

    def test_fails_when_app_deletion_times_out(self):
        current = {"name": "example"}
        module = FakeModule({"delete_timeout": 60, "force": True, "name": "example"})

        with (
            patch.object(apps, "get_app", return_value=current),
            patch.object(apps, "delete_result", return_value=None),
            patch.object(apps, "wait_for_app_absent", return_value=current),
            patch.object(apps, "wait_deadline", return_value=70),
            patch.object(apps, "seconds_left", return_value=50),
            self.assertRaises(ModuleFail) as raised,
        ):
            apps.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Deletion of app 'example' timed out",
        )

    def test_check_mode_does_not_create(self):
        module = FakeModule({"name": "example", "org_slug": "linuxhq"}, check_mode=True)

        with (
            patch.object(apps, "get_app", return_value=None),
            patch.object(apps, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_present(module, {})

        post.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["app"], {"name": "example"})

    def test_create_tolerates_read_after_write_lag(self):
        module = FakeModule({"name": "example", "network": None, "org_slug": "linuxhq"})

        with (
            patch.object(apps, "get_app", return_value=None) as get,
            patch.object(apps, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_present(module, {})

        post.assert_called_once_with({}, "/apps", {"name": "example", "org_slug": "linuxhq"})
        self.assertEqual(get.call_count, 2)
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["app"], {"name": "example"})

    def test_check_mode_does_not_delete(self):
        current = {"name": "example"}
        module = FakeModule({"name": "example", "delete_timeout": 60}, check_mode=True)

        with (
            patch.object(apps, "get_app", return_value=current),
            patch.object(apps, "delete_result") as delete,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_absent(module, {})

        delete.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["app"], current)
