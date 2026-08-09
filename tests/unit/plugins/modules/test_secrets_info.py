# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import secrets_info
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


class SecretsInfoTests(TestCase):
    def test_lists_secret_metadata_without_values(self):
        module = FakeModule({"app_name": "example/app"})
        response = {
            "secrets": [{"name": "APP_SECRET", "digest": "digest", "value": "secret"}]
        }

        with (
            patch.object(secrets_info, "get_result", return_value=response) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets_info.list_resources(module, {})

        get.assert_called_once_with(
            {},
            "/apps/example%2Fapp/secrets",
            default={"secrets": []},
            ok_statuses=[404],
        )
        self.assertEqual(
            raised.exception.values["secrets"],
            [{"name": "APP_SECRET", "digest": "digest"}],
        )

    def test_rejects_malformed_response(self):
        module = FakeModule({"app_name": "example"})

        for response in (
            {"secrets": None},
            {"secrets": [None]},
            {"secrets": [{}]},
            {"secrets": [{"name": "APP_SECRET"}]},
            {"secrets": [{"name": "APP_SECRET", "digest": 1}]},
            {
                "secrets": [
                    {
                        "name": "APP_SECRET",
                        "digest": "digest",
                        "updated_at": None,
                    }
                ]
            },
            {
                "secrets": [
                    {
                        "name": "APP_SECRET",
                        "digest": "digest",
                        "updated_at": "",
                    }
                ]
            },
        ):
            with (
                self.subTest(response=response),
                patch.object(secrets_info, "get_result", return_value=response),
                self.assertRaises(ModuleFail) as raised,
            ):
                secrets_info.list_resources(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "Fly.io API returned malformed data while listing secrets "
                "for app 'example'",
            )
