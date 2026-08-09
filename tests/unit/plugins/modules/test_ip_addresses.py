# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import ip_addresses
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
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
        self.assertIn("created_at: createdAt", query.call_args.args[1])
        self.assertEqual(
            raised.exception.values["ip_address"],
            {"address": "1.2.3.4", "region": "", "type": "shared_v4"},
        )

    def test_rejects_malformed_allocation_response(self):
        module = FakeModule({"app_name": "example", "region": "", "type": "v4"})

        for response in (
            {"allocateIpAddress": []},
            {"allocateIpAddress": {"ipAddress": {"address": "::1", "type": "v6"}}},
            {
                "allocateIpAddress": {
                    "ipAddress": {
                        "address": "1.2.3.4",
                        "region": "iad",
                        "type": "v4",
                    }
                }
            },
        ):
            with (
                self.subTest(response=response),
                patch.object(ip_addresses, "get_ip_addresses", return_value=[]),
                patch.object(
                    ip_addresses,
                    "graphql_request",
                    return_value=response,
                ),
                self.assertRaises(ModuleFail) as raised,
            ):
                ip_addresses.ensure_present(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "fly.io API returned an empty or malformed response during IP allocation",
            )

    def test_rejects_malformed_allocation_region(self):
        module = FakeModule({"app_name": "example", "region": "", "type": "private_v6"})
        response = {
            "allocateIpAddress": {
                "ipAddress": {
                    "address": "fdaa::1",
                    "region": [],
                    "type": "private_v6",
                }
            }
        }

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[]),
            patch.object(ip_addresses, "graphql_request", return_value=response),
            self.assertRaises(ModuleFail),
        ):
            ip_addresses.ensure_present(module, {})

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
            patch.object(
                ip_addresses,
                "graphql_request",
                return_value={"releaseIpAddress": {"clientMutationId": None}},
            ) as query,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        self.assertEqual(
            query.call_args.args[2],
            {"input": {"appId": "example", "ip": "1.2.3.4"}},
        )
        self.assertIn("clientMutationId", query.call_args.args[1])
        self.assertNotIn("app {", query.call_args.args[1])
        self.assertTrue(raised.exception.values["changed"])

    def test_missing_app_is_already_absent(self):
        module = FakeModule(
            {
                "address": "1.2.3.4",
                "app_name": "missing",
                "region": "",
                "type": None,
            }
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[]) as get,
            patch.object(ip_addresses, "graphql_request") as query,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        get.assert_called_once_with({}, "missing", missing_ok=True)
        query.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])

    def test_rejects_ambiguous_type_release(self):
        addresses = [
            {"address": "1.2.3.4", "region": "ord", "type": "v4"},
            {"address": "1.2.3.5", "region": "ord", "type": "v4"},
        ]
        module = FakeModule(
            {
                "address": None,
                "app_name": "example",
                "region": "ord",
                "type": "v4",
            }
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=addresses),
            patch.object(ip_addresses, "graphql_request") as query,
            self.assertRaises(ModuleFail) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        query.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "Multiple IP addresses match type and region; specify address",
        )

    def test_rejects_malformed_release_response(self):
        current = {"address": "1.2.3.4", "region": "ord", "type": "v4"}
        module = FakeModule(
            {
                "address": "1.2.3.4",
                "app_name": "example",
                "region": "",
                "type": None,
            }
        )

        for response in (
            {"releaseIpAddress": None},
            {"releaseIpAddress": {}},
            {"releaseIpAddress": {"clientMutationId": []}},
        ):
            with (
                self.subTest(response=response),
                patch.object(ip_addresses, "get_ip_addresses", return_value=[current]),
                patch.object(
                    ip_addresses,
                    "graphql_request",
                    return_value=response,
                ),
                self.assertRaises(ModuleFail) as raised,
            ):
                ip_addresses.ensure_absent(module, {})

            self.assertEqual(
                raised.exception.values["msg"],
                "fly.io API returned an empty or malformed response during IP release",
            )
