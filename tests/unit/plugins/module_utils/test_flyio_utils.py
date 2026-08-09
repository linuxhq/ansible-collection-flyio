# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    _MISSING,
    FlyioApiError,
    authorization_header,
    get_ip_addresses,
    get_resource,
    get_result,
    graphql_request,
    list_all,
    values_differ,
    wait_for_app_absent,
    wait_for_machine,
    wait_for_machine_settled,
    wait_for_volume,
)


class FlyioUtilsTests(TestCase):
    def test_ip_addresses_accept_missing_app_when_requested(self):
        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.graphql_request",
            side_effect=FlyioApiError("Could not find App"),
        ):
            self.assertEqual(get_ip_addresses({}, "missing", missing_ok=True), [])

        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.graphql_request",
            return_value={"app": None},
        ):
            self.assertEqual(get_ip_addresses({}, "missing", missing_ok=True), [])

    def test_ip_addresses_reject_missing_or_malformed_app(self):
        for app in (None, []):
            with (
                self.subTest(app=app),
                patch(
                    "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.graphql_request",
                    return_value={"app": app},
                ),
                self.assertRaises(FlyioApiError),
            ):
                get_ip_addresses({}, "example")

    def test_ip_addresses_reject_malformed_address_entries(self):
        for address in ({"type": "v4"}, {"address": "1.2.3.4", "region": []}):
            with (
                self.subTest(address=address),
                patch(
                    "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.graphql_request",
                    return_value={
                        "app": {
                            "ipAddresses": {"nodes": [address]},
                            "sharedIpAddress": None,
                        }
                    },
                ),
                self.assertRaises(FlyioApiError),
            ):
                get_ip_addresses({}, "example")

    def test_ip_addresses_reject_malformed_shared_address(self):
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.graphql_request",
                return_value={
                    "app": {
                        "ipAddresses": {"nodes": []},
                        "sharedIpAddress": False,
                    }
                },
            ),
            self.assertRaises(FlyioApiError),
        ):
            get_ip_addresses({}, "example")

    def test_rejects_malformed_graphql_response_shapes(self):
        for content in (b"[]", b'{"data": null}'):
            with (
                self.subTest(content=content),
                patch(
                    "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.open_url"
                ) as open_url,
                self.assertRaises(FlyioApiError),
            ):
                open_url.return_value.read.return_value = content
                graphql_request({"headers": {}}, "query { viewer { id } }")

    def test_uses_flyv1_for_fly_machine_tokens(self):
        self.assertEqual(authorization_header("fm2_example"), "FlyV1 fm2_example")
        self.assertEqual(authorization_header("fm1r_example"), "FlyV1 fm1r_example")
        self.assertEqual(
            authorization_header("fo1_example,fm2_example"),
            "FlyV1 fo1_example,fm2_example",
        )

    def test_preserves_explicit_authorization_scheme(self):
        self.assertEqual(authorization_header("FlyV1 fm2_example"), "FlyV1 fm2_example")
        self.assertEqual(authorization_header("Bearer example"), "Bearer example")

    def test_purge_detects_removed_dictionary_keys(self):
        current = {"KEEP": "value", "REMOVE": "value"}

        self.assertFalse(values_differ(current, {"KEEP": "value"}))
        self.assertTrue(values_differ(current, {"KEEP": "value"}, purge=True))
        self.assertTrue(values_differ(current, {}, purge=True))

    def test_purge_ignores_nested_api_defaults(self):
        current = {"check": {"port": 8080, "timeout": "2s"}}

        self.assertFalse(values_differ(current, {"check": {"port": 8080}}, purge=True))

    def test_stopped_wait_includes_instance_id(self):
        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request"
        ) as request:
            wait_for_machine(
                {},
                "example",
                "machine-one",
                "stopped",
                60,
                instance_id="instance-one",
            )

        request.assert_called_once_with(
            {},
            "get",
            "/apps/example/machines/machine-one/wait?state=stopped&timeout=60&instance_id=instance-one",
            ok_statuses=None,
            timeout=70,
        )

    def test_machine_wait_rejects_malformed_instance_id(self):
        with self.assertRaises(FlyioApiError):
            wait_for_machine({}, "example", "machine-one", instance_id=[])

    def test_machine_settle_waits_for_stable_state(self):
        updating = {"id": "machine-one", "state": "updating"}
        started = {"id": "machine-one", "state": "started"}
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.monotonic",
                side_effect=[0, 0, 0, 0],
            ),
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.get_resource",
                side_effect=[updating, started],
            ) as get,
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.sleep"
            ),
        ):
            result = wait_for_machine_settled(
                {},
                "example",
                "machine-one",
                {"creating", "starting", "updating"},
                timeout=5,
            )

        self.assertEqual(get.call_count, 2)
        self.assertEqual(result, started)

    def test_get_result_passes_timeout(self):
        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
            return_value={"id": "example"},
        ) as request:
            result = get_result({}, "/apps/example", timeout=4)

        request.assert_called_once_with(
            {}, "get", "/apps/example", ok_statuses=None, timeout=4
        )
        self.assertEqual(result, {"id": "example"})

    def test_get_result_distinguishes_empty_success_from_missing(self):
        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
            side_effect=[None, _MISSING],
        ):
            self.assertIsNone(get_result({}, "/apps/example", default={}))
            self.assertEqual(get_result({}, "/apps/missing", default={}), {})

    def test_get_resource_rejects_missing_or_malformed_resource(self):
        for result in (None, [], {}, {"name": []}):
            with (
                self.subTest(result=result),
                patch(
                    "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                    return_value=result,
                ),
                self.assertRaises(FlyioApiError),
            ):
                get_resource({}, "/apps/example", required_field="name")

    def test_get_resource_accepts_tolerated_missing_resource(self):
        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
            return_value=_MISSING,
        ):
            self.assertIsNone(get_resource({}, "/apps/missing", ok_statuses=[404]))

    def test_get_resource_rejects_empty_success_with_tolerated_status(self):
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                return_value=None,
            ),
            self.assertRaises(FlyioApiError),
        ):
            get_resource({}, "/apps/example", ok_statuses=[404])

    def test_get_resource_rejects_unexpected_identity(self):
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                return_value={"id": "machine-two"},
            ),
            self.assertRaises(FlyioApiError),
        ):
            get_resource(
                {},
                "/apps/example/machines/machine-one",
                required_field="id",
                expected_value="machine-one",
            )

    def test_get_resource_rejects_malformed_required_fields(self):
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                return_value={"id": "machine-one", "state": []},
            ),
            self.assertRaises(FlyioApiError),
        ):
            get_resource(
                {},
                "/apps/example/machines/machine-one",
                required_field="id",
                required_fields=("state",),
            )

    def test_list_all_accepts_missing_parent(self):
        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
            return_value=_MISSING,
        ) as request:
            result = list_all({}, "/apps/missing/machines", ok_statuses=[404])

        request.assert_called_once_with(
            {}, "get", "/apps/missing/machines", ok_statuses=[404]
        )
        self.assertEqual(result, [])

    def test_list_all_rejects_empty_success_with_tolerated_status(self):
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                return_value=None,
            ),
            self.assertRaises(FlyioApiError),
        ):
            list_all({}, "/apps/example/machines", ok_statuses=[404])

    def test_list_all_rejects_malformed_resources(self):
        for result in (None, {"id": "machine-one"}, ["machine-one"]):
            with (
                self.subTest(result=result),
                patch(
                    "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                    return_value=result,
                ),
                self.assertRaises(FlyioApiError),
            ):
                list_all({}, "/apps/example/machines")

    def test_list_all_rejects_resources_without_identity(self):
        for result in ([{}], [{"id": []}]):
            with (
                self.subTest(result=result),
                patch(
                    "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                    return_value=result,
                ),
                self.assertRaises(FlyioApiError),
            ):
                list_all({}, "/apps/example/machines", required_field="id")

    def test_list_all_rejects_malformed_required_fields(self):
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                return_value=[{"id": "machine-one", "name": "worker", "state": []}],
            ),
            self.assertRaises(FlyioApiError),
        ):
            list_all(
                {},
                "/apps/example/machines",
                required_field="id",
                required_fields=("name", "state"),
            )

    def test_app_wait_does_not_poll_past_deadline(self):
        app = {"name": "example"}
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.monotonic",
                side_effect=[10, 11, 15, 15],
            ),
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.get_resource",
                return_value=app,
            ) as get,
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.sleep"
            ),
        ):
            result = wait_for_app_absent({}, "example", timeout=5)

        get.assert_called_once_with(
            {},
            "/apps/example",
            ok_statuses=[404],
            timeout=4,
            required_field="name",
            expected_value="example",
        )
        self.assertEqual(result, app)

    def test_volume_wait_does_not_poll_past_deadline(self):
        volume = {"id": "volume-one", "state": "creating"}
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.monotonic",
                side_effect=[10, 11, 15, 15],
            ),
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.get_resource",
                return_value=volume,
            ) as get,
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.sleep"
            ),
        ):
            result = wait_for_volume({}, "example", "volume-one", timeout=5)

        get.assert_called_once_with(
            {},
            "/apps/example/volumes/volume-one",
            ok_statuses=None,
            timeout=4,
            required_field="id",
            expected_value="volume-one",
            required_fields=("state",),
        )
        self.assertEqual(result, volume)

    def test_destroyed_machine_wait_accepts_missing_machine(self):
        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request"
        ) as request:
            wait_for_machine({}, "example", "machine-one", "destroyed", 60)

        request.assert_called_once_with(
            {},
            "get",
            "/apps/example/machines/machine-one/wait?state=destroyed&timeout=60",
            ok_statuses=[404],
            timeout=70,
        )

    def test_volume_wait_requires_target_size(self):
        old = {"id": "volume-one", "size_gb": 1, "state": "created"}
        extended = {"id": "volume-one", "size_gb": 2, "state": "created"}
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.monotonic",
                side_effect=[0, 0, 0, 0],
            ),
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.get_resource",
                side_effect=[old, extended],
            ) as get,
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.sleep"
            ),
        ):
            result = wait_for_volume({}, "example", "volume-one", timeout=5, size_gb=2)

        self.assertEqual(get.call_count, 2)
        self.assertEqual(result, extended)

    def test_volume_wait_rejects_malformed_size(self):
        volume = {"id": "volume-one", "size_gb": "2", "state": "created"}
        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.time.monotonic",
                side_effect=[0, 0],
            ),
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.get_resource",
                return_value=volume,
            ),
            self.assertRaises(FlyioApiError),
        ):
            wait_for_volume({}, "example", "volume-one", timeout=5, size_gb=2)
