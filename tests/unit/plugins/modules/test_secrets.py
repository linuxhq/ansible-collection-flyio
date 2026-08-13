# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    FlyioApiError,
)
from ansible_collections.linuxhq.flyio.plugins.modules import secrets
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


class SecretsTests(TestCase):
    def test_secret_path_is_escaped(self):
        self.assertEqual(
            secrets.secret_path("example/app", "APP SECRET"),
            "/apps/example%2Fapp/secrets/APP%20SECRET",
        )

    def test_sets_new_secret_without_returning_value(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET", "value": "secret"})
        response = {
            "name": "APP_SECRET",
            "value": "secret",
            "digest": "new",
            "version": 2,
        }

        with (
            patch.object(secrets, "get_resource", return_value=None),
            patch.object(secrets, "post_result", return_value=response) as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_present(module, {})

        post.assert_called_once_with({}, "/apps/example/secrets/APP_SECRET", {"value": "secret"})
        self.assertTrue(raised.exception.values["changed"])
        self.assertNotIn("value", raised.exception.values["secret"])
        self.assertEqual(raised.exception.values["version"], 2)

    def test_identical_secret_is_unchanged(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET", "value": "secret"})
        current = {"name": "APP_SECRET", "digest": "same"}
        response = {"name": "APP_SECRET", "digest": "same"}

        with (
            patch.object(secrets, "get_resource", return_value=current),
            patch.object(secrets, "post_result", return_value=response) as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_present(module, {})

        post.assert_called_once_with({}, "/apps/example/secrets/APP_SECRET", {"value": "secret"})
        self.assertFalse(raised.exception.values["changed"])

    def test_changed_secret_is_set(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET", "value": "secret"})
        current = {"name": "APP_SECRET", "digest": "old"}
        response = {"name": "APP_SECRET", "digest": "new"}

        with (
            patch.object(secrets, "get_resource", return_value=current),
            patch.object(secrets, "post_result", return_value=response),
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_present(module, {})

        self.assertTrue(raised.exception.values["changed"])

    def test_rejects_malformed_set_response(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET", "value": "secret"})

        for response in (
            [],
            {"digest": "digest"},
            {"digest": "", "name": "APP_SECRET"},
            {"digest": "digest", "name": "OTHER_SECRET"},
            {"digest": "digest", "name": "APP_SECRET", "version": "two"},
            {"digest": "digest", "name": "APP_SECRET", "version": -1},
            {"created_at": "", "digest": "digest", "name": "APP_SECRET"},
            {"created_at": 1, "digest": "digest", "name": "APP_SECRET"},
        ):
            with (
                self.subTest(response=response),
                patch.object(secrets, "get_resource", return_value=None),
                patch.object(secrets, "post_result", return_value=response),
                self.assertRaises(ModuleFail) as raised,
            ):
                secrets.ensure_present(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "Fly.io API returned malformed data while setting secret 'APP_SECRET' for app 'example'",
            )

    def test_rejects_malformed_current_secret_timestamps(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET", "value": "secret"})

        with (
            patch.object(
                secrets,
                "get_resource",
                return_value={
                    "created_at": 1,
                    "digest": "current",
                    "name": "APP_SECRET",
                },
            ),
            patch.object(secrets, "post_result") as post,
            self.assertRaises(FlyioApiError),
        ):
            secrets.ensure_present(module, {})

        post.assert_not_called()

    def test_rejects_malformed_read_before_setting(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET", "value": "secret"})

        with (
            patch.object(
                secrets,
                "get_resource",
                side_effect=FlyioApiError("malformed"),
            ),
            patch.object(secrets, "post_result") as post,
            self.assertRaises(FlyioApiError),
        ):
            secrets.ensure_present(module, {})

        post.assert_not_called()

    def test_check_mode_does_not_set_secret(self):
        module = FakeModule(
            {"app_name": "example", "name": "APP_SECRET", "value": "secret"},
            check_mode=True,
        )

        with (
            patch.object(
                secrets,
                "get_resource",
                return_value={"name": "APP_SECRET", "digest": "current"},
            ),
            patch.object(secrets, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_present(module, {})

        post.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])

    def test_check_mode_omits_missing_secret_metadata(self):
        module = FakeModule(
            {"app_name": "example", "name": "APP_SECRET", "value": "secret"},
            check_mode=True,
        )

        with (
            patch.object(secrets, "get_resource", return_value=None),
            patch.object(secrets, "post_result") as post,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_present(module, {})

        post.assert_not_called()
        self.assertNotIn("secret", raised.exception.values)

    def test_missing_secret_is_unchanged_when_absent(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET"})

        with (
            patch.object(secrets, "get_resource", return_value=None),
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
            patch.object(secrets, "get_resource", return_value=current),
            patch.object(secrets, "delete_result", return_value={"version": 3}) as delete,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets.ensure_absent(module, {})

        delete.assert_called_once_with({}, "/apps/example/secrets/APP_SECRET", ok_statuses=[404])
        self.assertTrue(raised.exception.values["changed"])
        self.assertNotIn("value", raised.exception.values["secret"])
        self.assertEqual(raised.exception.values["version"], 3)

    def test_rejects_malformed_remove_response(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET"})

        for response in (["invalid"], {"version": "three"}, {"version": -1}):
            with (
                self.subTest(response=response),
                patch.object(
                    secrets,
                    "get_resource",
                    return_value={"digest": "current", "name": "APP_SECRET"},
                ),
                patch.object(secrets, "delete_result", return_value=response),
                self.assertRaises(ModuleFail) as raised,
            ):
                secrets.ensure_absent(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "Fly.io API returned malformed data while removing secret 'APP_SECRET' from app 'example'",
            )

    def test_rejects_malformed_read_before_removing(self):
        module = FakeModule({"app_name": "example", "name": "APP_SECRET"})

        with (
            patch.object(
                secrets,
                "get_resource",
                side_effect=FlyioApiError("malformed"),
            ),
            patch.object(secrets, "delete_result") as delete,
            self.assertRaises(FlyioApiError),
        ):
            secrets.ensure_absent(module, {})

        delete.assert_not_called()
