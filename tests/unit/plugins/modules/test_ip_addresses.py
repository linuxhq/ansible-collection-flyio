# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import ip_addresses
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
)


class IpAddressesTests(TestCase):
    def test_finds_address_by_type_and_region(self):
        addresses = [
            {"address": "one", "region": "ord", "type": "v4"},
            {"address": "two", "region": "global", "type": "v6"},
        ]

        self.assertEqual(
            ip_addresses.find_ip_by_type_and_region(addresses, "v6", ""),
            addresses[1],
        )

    def test_existing_address_is_unchanged(self):
        current = {"address": "1.2.3.4", "region": "ord", "type": "v4"}
        module = FakeModule({"app_name": "example", "region": "ord", "type": "v4"})

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[current]),
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_allocates_shared_address(self):
        module = FakeModule({"app_name": "example", "region": "", "type": "shared_v4"})
        response = {"allocateIpAddress": {"app": {"sharedIpAddress": "1.2.3.4"}}}

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[]),
            patch.object(
                ip_addresses, "graphql_request", return_value=response
            ) as query,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        self.assertEqual(
            query.call_args.args[2],
            {"input": {"appId": "example", "type": "shared_v4"}},
        )
        self.assertEqual(
            raised.exception.values["ip_address"],
            {"address": "1.2.3.4", "region": "", "type": "shared_v4"},
        )

    def test_releases_address(self):
        current = {"address": "1.2.3.4", "region": "ord", "type": "v4"}
        module = FakeModule(
            {
                "address": "1.2.3.4",
                "app_name": "example",
                "region": "",
                "type": None,
            }
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[current]),
            patch.object(ip_addresses, "graphql_request") as query,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        self.assertEqual(
            query.call_args.args[2],
            {"input": {"appId": "example", "ip": "1.2.3.4"}},
        )
        self.assertTrue(raised.exception.values["changed"])
