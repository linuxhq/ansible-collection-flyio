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
    def test_finds_equivalent_ipv6_address(self):
        current = {
            "address": "2001:db8::1",
            "region": "",
            "type": "v6",
        }

        self.assertIs(
            ip_addresses.find_ip_by_address(
                [current], "2001:0db8:0000:0000:0000:0000:0000:0001"
            ),
            current,
        )

    def test_filters_addresses_by_type_and_region(self):
        addresses = [
            {"address": "one", "region": "ord", "type": "v4"},
            {"address": "two", "region": "global", "type": "v6"},
        ]

        self.assertEqual(
            ip_addresses.ips_by_type_and_region(addresses, "v6", ""),
            [addresses[1]],
        )
        self.assertEqual(
            ip_addresses.ips_by_type_and_region(
                [{"address": "private", "region": "ord", "type": "private_v6"}],
                "private_v6",
                "iad",
            ),
            [],
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

    def test_allocates_private_address_in_requested_region(self):
        module = FakeModule(
            {"app_name": "example", "region": "iad", "type": "private_v6"}
        )
        response = {
            "allocateIpAddress": {
                "ipAddress": {
                    "address": "fdaa::1",
                    "region": "iad",
                    "type": "private_v6",
                }
            }
        }

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[]),
            patch.object(
                ip_addresses, "graphql_request", return_value=response
            ) as query,
            self.assertRaises(ModuleExit),
        ):
            ip_addresses.ensure_present(module, {})

        self.assertEqual(
            query.call_args.args[2],
            {
                "input": {
                    "appId": "example",
                    "region": "iad",
                    "type": "private_v6",
                }
            },
        )

    def test_normalizes_global_region_before_allocation(self):
        module = FakeModule({"app_name": "example", "region": "global", "type": "v6"})
        response = {
            "allocateIpAddress": {
                "ipAddress": {
                    "address": "2001:db8::1",
                    "region": "global",
                    "type": "v6",
                }
            }
        }

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
            {"input": {"appId": "example", "type": "v6"}},
        )
        self.assertEqual(raised.exception.values["ip_address"]["region"], "")

    def test_rejects_regional_shared_address_before_lookup(self):
        module = FakeModule(
            {"app_name": "example", "region": "iad", "type": "shared_v4"}
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses") as get,
            self.assertRaises(ModuleFail) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        get.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "region must be global for type=shared_v4",
        )

    def test_rejects_whitespace_region_before_lookup(self):
        module = FakeModule(
            {"app_name": "example", "region": " ", "type": "private_v6"}
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses") as get,
            self.assertRaises(ModuleFail) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        get.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "region must not contain only whitespace",
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
            {
                "allocateIpAddress": {
                    "ipAddress": {
                        "address": "1.2.3.4",
                        "id": False,
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
                "Fly.io API returned malformed data while allocating a 'v4' "
                "address for app 'example'",
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

    def test_rejects_whitespace_region_for_address_release(self):
        module = FakeModule(
            {
                "address": "1.2.3.4",
                "app_name": "example",
                "region": " ",
                "type": None,
            }
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses") as get,
            self.assertRaises(ModuleFail) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        get.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "region must not contain only whitespace",
        )

    def test_rejects_region_for_address_release(self):
        module = FakeModule(
            {
                "address": "1.2.3.4",
                "app_name": "example",
                "region": "ord",
                "type": None,
            }
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses") as get,
            self.assertRaises(ModuleFail) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        get.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "region is valid only when type is specified",
        )

    def test_rejects_invalid_release_address_before_lookup(self):
        module = FakeModule(
            {
                "address": "not-an-ip",
                "app_name": "example",
                "region": "",
                "type": None,
            }
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses") as get,
            self.assertRaises(ModuleFail) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        get.assert_not_called()
        self.assertEqual(
            raised.exception.values["msg"],
            "address must be a valid IPv4 or IPv6 address",
        )

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
            "Multiple 'v4' addresses in region 'ord' match for app 'example'; "
            "specify address",
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
                "Fly.io API returned malformed data while releasing address "
                "'1.2.3.4' from app 'example'",
            )
