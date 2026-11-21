# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import secrets_info
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
)


class SecretsInfoTests(TestCase):
    def test_lists_secret_metadata(self):
        module = FakeModule({"app_name": "example/app"})
        response = {"secrets": [{"name": "APP_SECRET", "digest": "digest", "value": "secret"}]}

        with (
            patch.object(secrets_info, "get_resource", return_value=response) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            secrets_info.list_resources(module, {})

        get.assert_called_once_with(
            {},
            "/apps/example%2Fapp/secrets",
            ok_statuses=[404],
        )
        self.assertEqual(
            raised.exception.values["secrets"],
            response["secrets"],
        )

    def test_returns_listed_secrets_as_reported(self):
        module = FakeModule({"app_name": "example"})

        for response, expected in (
            (None, []),
            ({}, []),
            ({"secrets": None}, []),
            ({"secrets": [{"name": "APP_SECRET", "digest": 1}]}, [{"name": "APP_SECRET", "digest": 1}]),
        ):
            with (
                self.subTest(response=response),
                patch.object(secrets_info, "get_resource", return_value=response),
                self.assertRaises(ModuleExit) as raised,
            ):
                secrets_info.list_resources(module, {})

            self.assertEqual(raised.exception.values["secrets"], expected)
