# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    FlyioApiError,
)
from ansible_collections.linuxhq.flyio.plugins.modules import ip_addresses_info
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
)


class IpAddressesInfoTests(TestCase):
    def test_lists_addresses(self):
        addresses = [{"address": "1.2.3.4", "type": "v4"}]
        module = FakeModule({"app_name": "example"})

        with (
            patch.object(ip_addresses_info, "get_ip_addresses", return_value=addresses),
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses_info.list_resources(module, {})

        self.assertEqual(raised.exception.values["ip_addresses"], addresses)

    def test_missing_app_returns_empty_list(self):
        module = FakeModule({"app_name": "missing"})

        with (
            patch.object(
                ip_addresses_info,
                "get_ip_addresses",
                side_effect=FlyioApiError("Could not find app"),
            ),
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses_info.list_resources(module, {})

        self.assertEqual(raised.exception.values["ip_addresses"], [])

    def test_other_api_errors_surface(self):
        module = FakeModule({"app_name": "example"})
        error = FlyioApiError("service unavailable")

        with (
            patch.object(ip_addresses_info, "get_ip_addresses", side_effect=error),
            self.assertRaises(FlyioApiError) as raised,
        ):
            ip_addresses_info.list_resources(module, {})

        self.assertIs(raised.exception, error)
