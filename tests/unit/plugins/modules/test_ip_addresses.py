# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import FlyioApiError
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
            ip_addresses.find_ip_by_address([current], "2001:0db8:0000:0000:0000:0000:0000:0001"),
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
                [{"address": "private", "region": "global", "type": "private_v6"}],
                "private_v6",
                "",
            ),
            [{"address": "private", "region": "global", "type": "private_v6"}],
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
            patch.object(ip_addresses, "graphql_request", return_value=response) as query,
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

    def test_allocates_global_private_address(self):
        response = {
            "allocateIpAddress": {
                "ipAddress": {
                    "address": "fdaa::1",
                    "region": "global",
                    "type": "private_v6",
                }
            }
        }

        for region in ("", "global"):
            module = FakeModule({"app_name": "example", "region": region, "type": "private_v6"})

            with (
                self.subTest(region=region),
                patch.object(ip_addresses, "get_ip_addresses", return_value=[]),
                patch.object(ip_addresses, "graphql_request", return_value=response) as query,
                self.assertRaises(ModuleExit) as raised,
            ):
                ip_addresses.ensure_present(module, {})

            self.assertEqual(
                query.call_args.args[2],
                {"input": {"appId": "example", "type": "private_v6"}},
            )
            self.assertTrue(raised.exception.values["changed"])
            self.assertEqual(raised.exception.values["ip_address"], response["allocateIpAddress"]["ipAddress"])

    def test_existing_global_private_address_is_unchanged(self):
        current = {"address": "fdaa::1", "region": "global", "type": "private_v6"}
        module = FakeModule({"app_name": "example", "region": "", "type": "private_v6"})

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[current]),
            patch.object(ip_addresses, "graphql_request") as query,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        query.assert_not_called()
        self.assertFalse(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["ip_address"], current)

    def test_rejects_regional_private_address_before_lookup(self):
        for state in ("present", "absent"):
            module = FakeModule({"app_name": "example", "address": None, "region": "iad", "type": "private_v6"})

            with (
                self.subTest(state=state),
                patch.object(ip_addresses, "get_ip_addresses") as get,
                patch.object(ip_addresses, "graphql_request") as query,
                self.assertRaises(ModuleFail) as raised,
            ):
                getattr(ip_addresses, f"ensure_{state}")(module, {})

            get.assert_not_called()
            query.assert_not_called()
            self.assertEqual(
                raised.exception.values["msg"],
                "region must be global for type=private_v6",
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
            patch.object(ip_addresses, "graphql_request", return_value=response) as query,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        self.assertEqual(
            query.call_args.args[2],
            {"input": {"appId": "example", "type": "v6"}},
        )
        self.assertEqual(raised.exception.values["ip_address"], response["allocateIpAddress"]["ipAddress"])

    def test_rejects_regional_shared_address_before_lookup(self):
        module = FakeModule({"app_name": "example", "region": "iad", "type": "shared_v4"})

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
        module = FakeModule({"app_name": "example", "region": " ", "type": "private_v6"})

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
                "Fly.io API returned malformed data while allocating a 'v4' address for app 'example'",
            )

    def test_malformed_allocation_returns_allocated_address(self):
        module = FakeModule({"app_name": "example", "region": "ord", "type": "v4"})
        allocated = {"address": "1.2.3.4", "region": "iad", "type": "v4"}

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[]),
            patch.object(
                ip_addresses,
                "graphql_request",
                return_value={"allocateIpAddress": {"ipAddress": allocated}},
            ),
            self.assertRaises(ModuleFail) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        self.assertEqual(raised.exception.values["ip_address"], allocated)

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

    def test_address_released_after_lookup_is_unchanged(self):
        current = {"address": "1.2.3.4", "region": "ord", "type": "v4"}
        module = FakeModule({"address": "1.2.3.4", "app_name": "example", "region": "", "type": None})
        error = FlyioApiError(
            "Release IP address '1.2.3.4' from app 'example' failed: Could not find IPAssignment",
            response_body=[
                {
                    "extensions": {"code": "NOT_FOUND"},
                    "message": "Could not find IPAssignment",
                    "path": ["releaseIpAddress"],
                }
            ],
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[current]),
            patch.object(ip_addresses, "graphql_request", side_effect=error),
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values,
            {"changed": False, "message": "IP address already released"},
        )

    def test_release_failure_is_raised(self):
        current = {"address": "1.2.3.4", "region": "ord", "type": "v4"}
        module = FakeModule({"address": "1.2.3.4", "app_name": "example", "region": "", "type": None})
        error = FlyioApiError("Release failed: forbidden", response_body=[{"message": "forbidden"}])

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[current]),
            patch.object(ip_addresses, "graphql_request", side_effect=error),
            self.assertRaises(FlyioApiError),
        ):
            ip_addresses.ensure_absent(module, {})

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
            "Multiple 'v4' addresses in region 'ord' match for app 'example'; specify address",
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
                "Fly.io API returned malformed data while releasing address '1.2.3.4' from app 'example'",
            )

    def test_allocation_sends_normalized_region(self):
        module = FakeModule({"app_name": "example", "region": " ORD ", "type": "v4"})
        allocated = {"address": "1.2.3.4", "region": "ord", "type": "v4"}

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[]),
            patch.object(
                ip_addresses,
                "graphql_request",
                return_value={"allocateIpAddress": {"ipAddress": allocated}},
            ) as query,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        self.assertEqual(
            query.call_args.args[2],
            {"input": {"appId": "example", "type": "v4", "region": "ord"}},
        )
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["ip_address"], allocated)

    def test_releases_shared_address(self):
        shared = {"address": "1.2.3.4", "region": "", "type": "shared_v4"}
        for requested in ({"address": "1.2.3.4", "type": None}, {"address": None, "type": "shared_v4"}):
            module = FakeModule({"app_name": "example", "region": "", **requested})
            with (
                self.subTest(requested=requested),
                patch.object(ip_addresses, "get_ip_addresses", return_value=[shared]),
                patch.object(
                    ip_addresses,
                    "graphql_request",
                    return_value={"releaseIpAddress": {"clientMutationId": None}},
                ) as query,
                self.assertRaises(ModuleExit) as raised,
            ):
                ip_addresses.ensure_absent(module, {})

            self.assertIn("releaseIpAddress", query.call_args.args[1])
            self.assertEqual(query.call_args.args[2], {"input": {"appId": "example", "ip": "1.2.3.4"}})
            self.assertTrue(raised.exception.values["changed"])
            self.assertEqual(raised.exception.values["ip_address"], shared)

    def test_region_case_and_whitespace_match_existing_address(self):
        current = {"address": "1.2.3.4", "region": "iad", "type": "v4"}
        for region in ("IAD", " iad "):
            module = FakeModule({"app_name": "example", "region": region, "type": "v4"})
            with (
                self.subTest(region=region),
                patch.object(ip_addresses, "get_ip_addresses", return_value=[current]),
                patch.object(ip_addresses, "graphql_request") as query,
                self.assertRaises(ModuleExit) as raised,
            ):
                ip_addresses.ensure_present(module, {})

            query.assert_not_called()
            self.assertFalse(raised.exception.values["changed"])

    def test_uppercase_global_region_is_global_for_shared_address(self):
        module = FakeModule({"app_name": "example", "region": "GLOBAL", "type": "shared_v4"})

        with (
            patch.object(
                ip_addresses,
                "get_ip_addresses",
                return_value=[{"address": "1.2.3.4", "type": "shared_v4", "region": ""}],
            ),
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        self.assertFalse(raised.exception.values["changed"])

    def test_check_mode_does_not_allocate(self):
        module = FakeModule({"app_name": "example", "region": "", "type": "v6"}, check_mode=True)

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[]),
            patch.object(ip_addresses, "graphql_request") as mutate,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_present(module, {})

        mutate.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["message"], "IP address would be allocated")

    def test_check_mode_does_not_release(self):
        current = {"id": "ip_one", "address": "2001:db8::1", "region": "", "type": "v6"}
        module = FakeModule(
            {"app_name": "example", "address": "2001:db8::1", "region": "", "type": None},
            check_mode=True,
        )

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=[current]),
            patch.object(ip_addresses, "graphql_request") as mutate,
            self.assertRaises(ModuleExit) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        mutate.assert_not_called()
        self.assertTrue(raised.exception.values["changed"])
        self.assertEqual(raised.exception.values["ip_address"], current)

    def test_ambiguous_global_release_names_global_region(self):
        addresses = [
            {"address": "2001:db8::1", "region": "global", "type": "v6"},
            {"address": "2001:db8::2", "region": "global", "type": "v6"},
        ]
        module = FakeModule({"app_name": "example", "address": None, "region": "", "type": "v6"})

        with (
            patch.object(ip_addresses, "get_ip_addresses", return_value=addresses),
            self.assertRaises(ModuleFail) as raised,
        ):
            ip_addresses.ensure_absent(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Multiple 'v6' addresses in region 'global' match for app 'example'; specify address",
        )
