# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import secrets
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
)


class SecretsTests(TestCase):
    def test_secret_path_is_escaped(self):
        self.assertEqual(
            secrets.secret_path("example/app", "APP SECRET"),
            "/apps/example%2Fapp/secrets/APP%20SECRET",
        )

    def test_sets_new_secret_without_returning_value(self):
        module = FakeModule(
            {"app_name": "example", "name": "APP_SECRET", "value": "secret"}
        )
        response = {
            "name": "APP_SECRET",
            "value": "secret",
            "digest": "new",
            "version": 2,
        }

        with (
            patch.object(secrets, "get_result", return_value=None),
            patch.object(secrets, "post_result", return_value=response) as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_present(module, {})

        post.assert_called_once_with(
            {}, "/apps/example/secrets/APP_SECRET", {"value": "secret"}
        )
        self.assertTrue(raised.exception.values["changed"])
        self.assertNotIn("value", raised.exception.values["secret"])
        self.assertEqual(raised.exception.values["version"], 2)

    def test_identical_secret_is_unchanged(self):
        module = FakeModule(
            {"app_name": "example", "name": "APP_SECRET", "value": "secret"}
        )
        current = {"name": "APP_SECRET", "digest": "same"}
        response = {**current, "version": 2}

        with (
            patch.object(secrets, "get_result", return_value=current),
            patch.object(secrets, "post_result", return_value=response),
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_check_mode_does_not_set_secret(self):
        module = FakeModule(
            {"app_name": "example", "name": "APP_SECRET", "value": "secret"},
            check_mode=True,
        )

        with (
            patch.object(secrets, "get_result", return_value={"digest": "current"}),
            patch.object(secrets, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_present(module, {})

        post.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])

    def test_missing_secret_is_unchanged_when_absent(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET"})

        with (
            patch.object(secrets, "get_result", return_value=None),
            patch.object(secrets, "delete_result") as delete,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_absent(module, {})

        delete.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_removes_secret(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET"})
        current = {"name": "APP_SECRET", "digest": "current", "value": "secret"}

        with (
            patch.object(secrets, "get_result", return_value=current),
            patch.object(
                secrets, "delete_result", return_value={"version": 3}
            ) as delete,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_absent(module, {})

        delete.assert_called_once_with({}, "/apps/example/secrets/APP_SECRET")
        self.assertTrue(raised.exception.values["changed"])
        self.assertNotIn("value", raised.exception.values["secret"])
        self.assertEqual(raised.exception.values["version"], 3)
