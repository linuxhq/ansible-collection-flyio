# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import json
from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from ansible.module_utils.urls import ConnectionError as AnsibleConnectionError

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    _MISSING,
    FlyioApiError,
    api_request,
    authorization_header,
    flyio_client,
    flyio_path,
    get_ip_addresses,
    get_resource,
    get_result,
    graphql_request,
    list_all,
    require_positive,
    sanitize_machine,
    wait_for_app_absent,
    wait_for_machine,
    wait_for_machine_settled,
    wait_for_volume,
)

FLYIO_UTILS = "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils"


class FlyioUtilsTests(TestCase):
    def test_positive_integer_validation_rejects_booleans(self):
        module = Mock(params={"timeout": True})
        module.fail_json.side_effect = RuntimeError

        with self.assertRaises(RuntimeError):
            require_positive(module, "timeout")

        module.fail_json.assert_called_once_with(msg="timeout must be greater than zero")

    def test_encodes_api_path_components(self):
        self.assertEqual(
            flyio_path("apps", "example/app", "machines", "id?version=1"),
            "/apps/example%2Fapp/machines/id%3Fversion%3D1",
        )

    def test_client_rejects_empty_resource_identifiers(self):
        for name in ("address", "app_name", "id", "name", "network", "org_slug"):
            module = Mock(
                params={"api_token": "token", name: " \t"},
            )
            module.fail_json.side_effect = RuntimeError

            with (
                self.subTest(name=name),
                self.assertRaises(RuntimeError),
                flyio_client(module),
            ):
                pass

            module.fail_json.assert_called_once_with(msg=f"{name} must not be empty")

    def test_client_rejects_token_line_breaks(self):
        module = Mock(params={"api_token": "token\r\nInjected: value"})
        module.fail_json.side_effect = RuntimeError

        with self.assertRaises(RuntimeError), flyio_client(module):
            pass

        module.fail_json.assert_called_once_with(msg="api_token must not contain line breaks")

    def test_client_rejects_invalid_tokens(self):
        for token, message in (
            (None, "api_token is required"),
            (" ", "api_token is required"),
            ("token\tvalue", "api_token must not contain control characters"),
            ("Bearer ", "api_token credential must not be empty"),
            ("FlyV1", "api_token credential must not be empty"),
        ):
            module = Mock(params={"api_token": token})
            module.fail_json.side_effect = RuntimeError

            with (
                self.subTest(token=token),
                self.assertRaises(RuntimeError),
                flyio_client(module),
            ):
                pass

            module.fail_json.assert_called_once_with(msg=message)

    def test_client_strips_token_whitespace(self):
        module = Mock(params={"api_token": "  token  "})

        with flyio_client(module) as client:
            self.assertEqual(client["headers"]["Authorization"], "Bearer token")

    def test_client_converts_api_errors_to_module_failures(self):
        module = Mock(params={"api_token": "token"})
        module.fail_json.side_effect = RuntimeError

        with self.assertRaises(RuntimeError), flyio_client(module):
            raise FlyioApiError(
                "Request failed",
                status_code=422,
                response_body={"error": "invalid"},
            )

        module.fail_json.assert_called_once_with(
            msg="Request failed",
            error="Request failed",
            status_code=422,
            response={"error": "invalid"},
        )

    def test_encodes_json_request_bodies(self):
        with patch(f"{FLYIO_UTILS}.open_url") as open_url:
            open_url.return_value.read.side_effect = [b"{}", b'{"data": {}}']

            api_request({"headers": {}}, "post", "/apps", {"name": "example"})
            graphql_request({"headers": {}}, "query { viewer { id } }")

        rest_data = open_url.call_args_list[0].kwargs["data"]
        graphql_data = open_url.call_args_list[1].kwargs["data"]
        self.assertIsInstance(rest_data, bytes)
        self.assertEqual(json.loads(rest_data), {"name": "example"})
        self.assertIsInstance(graphql_data, bytes)
        self.assertEqual(
            json.loads(graphql_data),
            {"query": "query { viewer { id } }"},
        )

    def test_sanitizes_machine_configuration_without_mutating_source(self):
        machine = {
            "config": {
                "checks": {
                    "legacy": {
                        "headers": {"Authorization": ["secret"]},
                        "port": 8080,
                    },
                    "web": {
                        "headers": [{"name": "Authorization", "values": ["secret"]}],
                        "port": 8080,
                    },
                },
                "env": {"TOKEN": "secret"},
                "files": [{"guest_path": "/secret", "raw_value": "c2VjcmV0"}],
                "image": "example:latest",
                "services": [{"ports": [{"http_options": {"response": {"headers": {"Authorization": "secret"}}}}]}],
            },
            "headers": {"Authorization": "secret"},
            "id": "machine-one",
        }
        machine["incomplete_config"] = machine["config"]

        result = sanitize_machine(machine)

        for field in ("config", "incomplete_config"):
            self.assertNotIn("env", result[field])
            self.assertNotIn("raw_value", result[field]["files"][0])
            self.assertNotIn("headers", result[field]["checks"]["legacy"])
            self.assertNotIn("headers", result[field]["checks"]["web"])
            self.assertNotIn(
                "headers",
                result[field]["services"][0]["ports"][0]["http_options"]["response"],
            )
        self.assertIn("env", machine["config"])
        self.assertIn("raw_value", machine["config"]["files"][0])
        self.assertNotIn("headers", result)
        self.assertIn("headers", machine)

        malformed = {
            "config": [{"env": {"TOKEN": "secret"}}],
            "incomplete_config": [{"env": {"TOKEN": "secret"}}],
        }
        self.assertEqual(sanitize_machine(malformed), {})
        self.assertEqual(sanitize_machine([{"env": {"TOKEN": "secret"}}]), {})
        self.assertIsNone(sanitize_machine(None))

    def test_preserves_plain_text_http_error_response(self):
        error = HTTPError(
            "https://api.machines.dev/v1/apps/example",
            422,
            "Unprocessable Entity",
            {},
            BytesIO(b"invalid region"),
        )
        with (
            patch(
                f"{FLYIO_UTILS}.open_url",
                side_effect=error,
            ),
            self.assertRaises(FlyioApiError) as raised,
        ):
            api_request({"headers": {}}, "get", "/apps/example")

        self.assertEqual(raised.exception.response_body, "invalid region")
        self.assertIn("GET /apps/example failed", str(raised.exception))

    def test_wraps_ansible_connection_errors(self):
        for request, expected in (
            (
                lambda: api_request({"headers": {}}, "get", "/apps/example"),
                "GET /apps/example failed: TLS setup failed",
            ),
            (
                lambda: graphql_request(
                    {"headers": {}},
                    "query { viewer { id } }",
                    operation="Gather viewer",
                ),
                "Gather viewer failed: TLS setup failed",
            ),
        ):
            with (
                self.subTest(expected=expected),
                patch(
                    "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.open_url",
                    side_effect=AnsibleConnectionError("TLS setup failed"),
                ),
                self.assertRaises(FlyioApiError) as raised,
            ):
                request()

            self.assertEqual(str(raised.exception), expected)
            self.assertIsInstance(
                raised.exception.__cause__,
                AnsibleConnectionError,
            )

    def test_wraps_response_read_errors(self):
        for request, expected in (
            (
                lambda: api_request({"headers": {}}, "get", "/apps/example"),
                "GET /apps/example failed: read timed out",
            ),
            (
                lambda: graphql_request(
                    {"headers": {}},
                    "query { viewer { id } }",
                    operation="Gather viewer",
                ),
                "Gather viewer failed: read timed out",
            ),
        ):
            with (
                self.subTest(expected=expected),
                patch(f"{FLYIO_UTILS}.open_url") as open_url,
                self.assertRaises(FlyioApiError) as raised,
            ):
                open_url.return_value.read.side_effect = TimeoutError("read timed out")
                request()

            self.assertEqual(str(raised.exception), expected)
            self.assertIsInstance(raised.exception.__cause__, TimeoutError)

    def test_preserves_graphql_errors_with_operation_context(self):
        errors = [
            {"message": "App not found"},
            {"message": "Request identifier", "path": ["app"]},
        ]
        with (
            patch(f"{FLYIO_UTILS}.open_url") as open_url,
            self.assertRaises(FlyioApiError) as raised,
        ):
            open_url.return_value.read.return_value = json.dumps({"errors": errors}).encode()
            graphql_request(
                {"headers": {}},
                "query { app { id } }",
                operation="Gather app 'example'",
            )

        self.assertEqual(
            str(raised.exception),
            "Gather app 'example' failed: App not found",
        )
        self.assertEqual(raised.exception.response_body, errors)

    def test_ip_addresses_accept_missing_app_when_requested(self):
        with patch(
            f"{FLYIO_UTILS}.graphql_request",
            side_effect=FlyioApiError("Could not find App"),
        ):
            self.assertEqual(get_ip_addresses({}, "missing", missing_ok=True), [])

        with patch(
            f"{FLYIO_UTILS}.graphql_request",
            return_value={"app": None},
        ):
            self.assertEqual(get_ip_addresses({}, "missing", missing_ok=True), [])

    def test_ip_addresses_reject_missing_or_malformed_app(self):
        for app in (None, []):
            with (
                self.subTest(app=app),
                patch(
                    f"{FLYIO_UTILS}.graphql_request",
                    return_value={"app": app},
                ),
                self.assertRaises(FlyioApiError),
            ):
                get_ip_addresses({}, "example")

    def test_ip_addresses_reject_malformed_address_entries(self):
        for address in (
            None,
            {},
            {"type": "v4"},
            {"address": "not-an-ip", "type": "v4"},
            {"address": "not-an-ip", "type": "unknown"},
            {"address": "1.2.3.4", "type": []},
            {"address": "2001:db8::1", "type": "v4"},
            {"address": "1.2.3.4", "type": "v6"},
            {"address": "1.2.3.4", "region": []},
            {"address": "1.2.3.4", "region": " ", "type": "v4"},
            {"address": "1.2.3.4", "type": "v4", "id": False},
            {"address": "1.2.3.4", "type": "v4", "id": " "},
            {"address": "1.2.3.4", "type": "v4", "created_at": []},
        ):
            with (
                self.subTest(address=address),
                patch(
                    f"{FLYIO_UTILS}.graphql_request",
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
        for shared_address in (False, "", "not-an-ip", "2001:db8::1"):
            with (
                self.subTest(shared_address=shared_address),
                patch(
                    f"{FLYIO_UTILS}.graphql_request",
                    return_value={
                        "app": {
                            "ipAddresses": {"nodes": []},
                            "sharedIpAddress": shared_address,
                        }
                    },
                ),
                self.assertRaises(FlyioApiError),
            ):
                get_ip_addresses({}, "example")

    def test_ip_addresses_omit_unavailable_fields(self):
        with patch(
            "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.graphql_request",
            return_value={
                "app": {
                    "ipAddresses": {
                        "nodes": [
                            {
                                "address": "1.2.3.4",
                                "created_at": None,
                                "id": None,
                                "region": None,
                                "type": "v4",
                            },
                            {
                                "address": "2001:db8::1",
                                "region": "global",
                                "type": "v6",
                            },
                        ]
                    },
                    "sharedIpAddress": None,
                }
            },
        ):
            addresses = get_ip_addresses({}, "example")

        self.assertEqual(
            addresses,
            [
                {"address": "1.2.3.4", "type": "v4"},
                {"address": "2001:db8::1", "region": "", "type": "v6"},
            ],
        )

    def test_rejects_malformed_graphql_response_shapes(self):
        for content in (b"[]", b'{"data": null}'):
            with (
                self.subTest(content=content),
                patch(f"{FLYIO_UTILS}.open_url") as open_url,
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

    def test_stopped_wait_includes_instance_id(self):
        with patch(
            f"{FLYIO_UTILS}.api_request",
            return_value={"ok": True},
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
            ("/apps/example/machines/machine-one/wait?state=stopped&timeout=60&instance_id=instance-one"),
            ok_statuses=None,
            timeout=70,
        )

    def test_machine_wait_rejects_malformed_instance_id(self):
        for instance_id in ([], " "):
            with (
                self.subTest(instance_id=instance_id),
                self.assertRaises(FlyioApiError) as raised,
            ):
                wait_for_machine({}, "example", "machine-one", instance_id=instance_id)

            self.assertIn("Machine 'machine-one' in app 'example'", str(raised.exception))

    def test_machine_wait_requires_stopped_instance_id(self):
        with self.assertRaises(FlyioApiError) as raised:
            wait_for_machine({}, "example", "machine-one", state="stopped")

        self.assertIn("requires an instance ID", str(raised.exception))

    def test_machine_wait_rejects_unsuccessful_response(self):
        for result in (None, {}, {"ok": False}):
            with (
                self.subTest(result=result),
                patch(
                    "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                    return_value=result,
                ),
                self.assertRaises(FlyioApiError) as raised,
            ):
                wait_for_machine({}, "example", "machine-one")

            self.assertIn("Machine 'machine-one' in app 'example'", str(raised.exception))

    def test_machine_settle_waits_for_stable_state(self):
        updating = {"id": "machine-one", "state": "updating"}
        started = {"id": "machine-one", "state": "started"}
        with (
            patch(
                f"{FLYIO_UTILS}.time.monotonic",
                side_effect=[0, 0, 0, 0],
            ),
            patch(
                f"{FLYIO_UTILS}.get_resource",
                side_effect=[updating, started],
            ) as get,
            patch(f"{FLYIO_UTILS}.time.sleep"),
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
            f"{FLYIO_UTILS}.api_request",
            return_value={"id": "example"},
        ) as request:
            result = get_result({}, "/apps/example", timeout=4)

        request.assert_called_once_with({}, "get", "/apps/example", ok_statuses=None, timeout=4)
        self.assertEqual(result, {"id": "example"})

    def test_get_result_distinguishes_empty_success_from_missing(self):
        with patch(
            f"{FLYIO_UTILS}.api_request",
            side_effect=[None, _MISSING],
        ):
            self.assertIsNone(get_result({}, "/apps/example", default={}))
            self.assertEqual(get_result({}, "/apps/missing", default={}), {})

    def test_get_resource_rejects_missing_or_malformed_resource(self):
        for result in (None, [], {}, {"name": []}, {"name": " "}):
            with (
                self.subTest(result=result),
                patch(
                    f"{FLYIO_UTILS}.api_request",
                    return_value=result,
                ),
                self.assertRaises(FlyioApiError),
            ):
                get_resource({}, "/apps/example", required_field="name")

    def test_get_resource_accepts_tolerated_missing_resource(self):
        with patch(
            f"{FLYIO_UTILS}.api_request",
            return_value=_MISSING,
        ):
            self.assertIsNone(get_resource({}, "/apps/missing", ok_statuses=[404]))

    def test_get_resource_rejects_empty_success_with_tolerated_status(self):
        with (
            patch(
                f"{FLYIO_UTILS}.api_request",
                return_value=None,
            ),
            self.assertRaises(FlyioApiError),
        ):
            get_resource({}, "/apps/example", ok_statuses=[404])

    def test_get_resource_rejects_unexpected_identity(self):
        with (
            patch(
                f"{FLYIO_UTILS}.api_request",
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

    def test_get_resource_requires_identity_field_for_expected_value(self):
        with (
            patch(
                f"{FLYIO_UTILS}.api_request",
                return_value={"id": "machine-one"},
            ),
            self.assertRaises(FlyioApiError),
        ):
            get_resource(
                {},
                "/apps/example/machines/machine-one",
                expected_value="machine-one",
            )

    def test_get_resource_rejects_malformed_required_fields(self):
        with (
            patch(
                f"{FLYIO_UTILS}.api_request",
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
            f"{FLYIO_UTILS}.api_request",
            return_value=_MISSING,
        ) as request:
            result = list_all({}, "/apps/missing/machines", ok_statuses=[404])

        request.assert_called_once_with({}, "get", "/apps/missing/machines", ok_statuses=[404])
        self.assertEqual(result, [])

    def test_list_all_rejects_empty_success_with_tolerated_status(self):
        with (
            patch(
                f"{FLYIO_UTILS}.api_request",
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
                    f"{FLYIO_UTILS}.api_request",
                    return_value=result,
                ),
                self.assertRaises(FlyioApiError),
            ):
                list_all({}, "/apps/example/machines")

    def test_list_all_rejects_resources_without_identity(self):
        for result in ([{}], [{"id": []}], [{"id": " "}]):
            with (
                self.subTest(result=result),
                patch(
                    f"{FLYIO_UTILS}.api_request",
                    return_value=result,
                ),
                self.assertRaises(FlyioApiError),
            ):
                list_all({}, "/apps/example/machines", required_field="id")

    def test_list_all_rejects_malformed_required_fields(self):
        with (
            patch(
                f"{FLYIO_UTILS}.api_request",
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
                f"{FLYIO_UTILS}.time.monotonic",
                side_effect=[10, 11, 15, 15],
            ),
            patch(
                f"{FLYIO_UTILS}.get_resource",
                return_value=app,
            ) as get,
            patch(f"{FLYIO_UTILS}.time.sleep"),
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
                f"{FLYIO_UTILS}.time.monotonic",
                side_effect=[10, 11, 15, 15],
            ),
            patch(
                f"{FLYIO_UTILS}.get_resource",
                return_value=volume,
            ) as get,
            patch(f"{FLYIO_UTILS}.time.sleep"),
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
            f"{FLYIO_UTILS}.api_request",
            return_value=_MISSING,
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
                f"{FLYIO_UTILS}.time.monotonic",
                side_effect=[0, 0, 0, 0],
            ),
            patch(
                f"{FLYIO_UTILS}.get_resource",
                side_effect=[old, extended],
            ) as get,
            patch(f"{FLYIO_UTILS}.time.sleep"),
        ):
            result = wait_for_volume({}, "example", "volume-one", timeout=5, size_gb=2)

        self.assertEqual(get.call_count, 2)
        self.assertEqual(result, extended)

    def test_volume_wait_rejects_malformed_size(self):
        volume = {"id": "volume-one", "size_gb": "2", "state": "created"}
        with (
            patch(
                f"{FLYIO_UTILS}.time.monotonic",
                side_effect=[0, 0],
            ),
            patch(
                f"{FLYIO_UTILS}.get_resource",
                return_value=volume,
            ),
            self.assertRaises(FlyioApiError) as raised,
        ):
            wait_for_volume({}, "example", "volume-one", timeout=5, size_gb=2)

        self.assertIn("volume 'volume-one' in app 'example'", str(raised.exception))
