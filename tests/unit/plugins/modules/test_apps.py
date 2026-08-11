# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

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
            patch.object(apps, "get_resource") as get,
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
            patch.object(apps, "get_resource", return_value=current),
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_creates_app_with_network(self):
        module = FakeModule(
            {"name": "example", "network": "private", "org_slug": "linuxhq"}
        )
        created = {"name": "example"}

        with (
            patch.object(apps, "get_resource", side_effect=[None, created]),
            patch.object(apps, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_present(module, {})

        post.assert_called_once_with(
            {},
            "/apps",
            {"app_name": "example", "network": "private", "org_slug": "linuxhq"},
        )
        self.assertEqual(raised.exception.values["app"], created)

    def test_deletes_app(self):
        current = {"name": "example"}
        module = FakeModule({"delete_timeout": 120, "force": True, "name": "example"})

        with (
            patch.object(apps, "get_resource", return_value=current),
            patch.object(apps, "delete_result", return_value=None) as delete,
            patch.object(apps, "wait_for_app_absent", return_value=None) as wait,
            patch.object(apps.time, "monotonic", side_effect=[10, 30]),
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_absent(module, {})

        delete.assert_called_once_with(
            {}, "/apps/example?force=true", timeout=120, ok_statuses=[404]
        )
        wait.assert_called_once_with({}, "example", 100)
        self.assertTrue(raised.exception.values["changed"])
        self.assertNotIn("app", raised.exception.values)

    def test_fails_when_app_deletion_times_out(self):
        current = {"name": "example"}
        module = FakeModule({"delete_timeout": 60, "force": True, "name": "example"})

        with (
            patch.object(apps, "get_resource", return_value=current),
            patch.object(apps, "delete_result", return_value=None),
            patch.object(apps, "wait_for_app_absent", return_value=current),
            patch.object(apps.time, "monotonic", side_effect=[10, 20]),
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
            patch.object(apps, "get_resource", return_value=None),
            patch.object(apps, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            apps.ensure_present(module, {})

        post.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])
