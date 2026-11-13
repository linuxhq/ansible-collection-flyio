# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import http.client
import json
from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from ansible.module_utils.common.arg_spec import ArgumentSpecValidator
from ansible.module_utils.urls import ConnectionError as AnsibleConnectionError

from ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils import (
    _MISSING,
    FlyioApiError,
    api_request,
    api_token_option,
    authorization_header,
    flyio_client,
    flyio_path,
    get_app,
    get_ip_addresses,
    get_resource,
    graphql_not_found,
    graphql_request,
    list_all,
    require_nonempty,
    require_positive,
    wait_for_app_absent,
    wait_for_machine,
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

    def test_api_token_falls_back_to_environment(self):
        validator = ArgumentSpecValidator({"api_token": api_token_option()})

        with patch.dict("os.environ", {"FLY_API_TOKEN": "env-token"}):
            fallback = validator.validate({})
            explicit = validator.validate({"api_token": "param-token"})

        self.assertEqual(fallback.validated_parameters["api_token"], "env-token")
        self.assertEqual(explicit.validated_parameters["api_token"], "param-token")
        self.assertIn("env-token", fallback._no_log_values)

    def test_require_nonempty_rejects_blank_strings(self):
        module = Mock(params={"app_name": "app", "name": " \t"})
        module.fail_json.side_effect = RuntimeError

        with self.assertRaises(RuntimeError):
            require_nonempty(module, "app_name", "name")

        module.fail_json.assert_called_once_with(msg="name must not be empty")

    def test_require_nonempty_ignores_unset_options(self):
        module = Mock(params={"id": None})

        require_nonempty(module, "id", "name")

        module.fail_json.assert_not_called()

    def test_client_does_not_validate_resource_identifiers(self):
        module = Mock(params={"api_token": "token", "name": " "})

        with flyio_client(module):
            pass

        module.fail_json.assert_not_called()

    def test_client_rejects_token_line_breaks_as_control_characters(self):
        module = Mock(params={"api_token": "token\r\nInjected: value"})
        module.fail_json.side_effect = RuntimeError

        with self.assertRaises(RuntimeError), flyio_client(module):
            pass

        module.fail_json.assert_called_once_with(msg="api_token must not contain control characters")

    def test_client_rejects_invalid_tokens(self):
        for token, message in (
            (None, "api_token is required; set api_token or FLY_API_TOKEN"),
            (" ", "api_token is required; set api_token or FLY_API_TOKEN"),
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

    def test_ip_addresses_are_returned_as_reported(self):
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
                {"address": "1.2.3.4", "created_at": None, "id": None, "region": None, "type": "v4"},
                {"address": "2001:db8::1", "region": "global", "type": "v6"},
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
                version="instance-one",
            )

        request.assert_called_once_with(
            {},
            "get",
            ("/apps/example/machines/machine-one/wait?state=stopped&timeout=60&version=instance-one"),
            ok_statuses=None,
            timeout=70,
        )

    def test_machine_wait_rejects_malformed_instance_id(self):
        for instance_id in ([], " "):
            with (
                self.subTest(version=instance_id),
                self.assertRaises(FlyioApiError) as raised,
            ):
                wait_for_machine({}, "example", "machine-one", version=instance_id)

            self.assertIn("Machine 'machine-one' in app 'example'", str(raised.exception))

    def test_machine_wait_retries_timeout_with_remaining_budget(self):
        with (
            patch(f"{FLYIO_UTILS}.time.monotonic", side_effect=[0, 60, 120]),
            patch(
                f"{FLYIO_UTILS}.api_request",
                side_effect=[
                    FlyioApiError("timeout", status_code=408),
                    FlyioApiError("timeout", status_code=408),
                    {"ok": True},
                ],
            ) as request,
        ):
            wait_for_machine({}, "example", "machine-one", "stopped", 150, version="instance-one")

        self.assertEqual(request.call_count, 3)
        for call, seconds in zip(request.call_args_list, [60, 60, 30]):
            self.assertIn(f"state=stopped&timeout={seconds}&version=instance-one", call.args[2])
            self.assertEqual(call.kwargs["timeout"], seconds + 10)

    def test_machine_wait_stops_at_deadline(self):
        with (
            patch(f"{FLYIO_UTILS}.time.monotonic", side_effect=[0, 60, 90]),
            patch(f"{FLYIO_UTILS}.api_request", side_effect=FlyioApiError("timeout", status_code=408)) as request,
            self.assertRaises(FlyioApiError) as raised,
        ):
            wait_for_machine({}, "example", "machine-one", timeout=90)

        self.assertEqual(request.call_count, 2)
        self.assertIn("timed out", str(raised.exception))
        self.assertEqual(raised.exception.status_code, 408)

    def test_machine_wait_does_not_retry_other_errors(self):
        for status in (None, 401, 404, 500):
            error = FlyioApiError("failure", status_code=status)
            with (
                self.subTest(status=status),
                patch(f"{FLYIO_UTILS}.api_request", side_effect=error) as request,
                self.assertRaises(FlyioApiError) as raised,
            ):
                wait_for_machine({}, "example", "machine-one", timeout=120)

            request.assert_called_once()
            self.assertIs(raised.exception, error)

    def test_machine_wait_requires_stopped_instance_id(self):
        with self.assertRaises(FlyioApiError) as raised:
            wait_for_machine({}, "example", "machine-one", state="stopped")

        self.assertIn("requires a version", str(raised.exception))

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
                get_resource({}, "/apps/example", required_fields=("name",))

    def test_get_resource_reports_identity_mismatch(self):
        with (
            patch(f"{FLYIO_UTILS}.api_request", return_value={"name": "other"}),
            self.assertRaises(FlyioApiError) as raised,
        ):
            get_resource({}, "/apps/example", required_fields=("name",), expected={"name": "example"})

        self.assertEqual(
            str(raised.exception), "GET /apps/example returned a different resource: expected name='example'"
        )

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
                required_fields=("id",),
                expected={"id": "machine-one"},
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
                required_fields=("id", "state"),
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
                list_all({}, "/apps/example/machines", required_fields=("id",))

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
                required_fields=("id", "name", "state"),
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
            timeout=14,
            required_fields=("name",),
            expected={"name": "example"},
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
            timeout=14,
            required_fields=("id", "state"),
            expected={"id": "volume-one"},
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
            patch(f"{FLYIO_UTILS}.time.monotonic", return_value=0),
            patch(
                f"{FLYIO_UTILS}.get_resource",
                side_effect=[old, extended],
            ) as get,
            patch(f"{FLYIO_UTILS}.time.sleep"),
        ):
            result = wait_for_volume({}, "example", "volume-one", timeout=5, size_gb=2)

        self.assertEqual(get.call_count, 2)
        self.assertEqual(result, extended)

    def test_volume_wait_ends_on_stop_state(self):
        creating = {"id": "volume-one", "state": "creating"}
        deleting = {"id": "volume-one", "state": "scheduling_destroy"}
        with (
            patch(f"{FLYIO_UTILS}.time.monotonic", return_value=0),
            patch(f"{FLYIO_UTILS}.get_resource", side_effect=[creating, deleting]) as get,
            patch(f"{FLYIO_UTILS}.time.sleep"),
        ):
            result = wait_for_volume({}, "example", "volume-one", timeout=5, stop_states={"scheduling_destroy"})

        self.assertEqual(get.call_count, 2)
        self.assertEqual(result, deleting)

    def test_volume_wait_continues_through_states_outside_stop_states(self):
        deleting = {"id": "volume-one", "state": "destroying"}
        with (
            patch(f"{FLYIO_UTILS}.time.monotonic", return_value=0),
            patch(f"{FLYIO_UTILS}.get_resource", side_effect=[deleting, None]) as get,
            patch(f"{FLYIO_UTILS}.time.sleep"),
        ):
            result = wait_for_volume({}, "example", "volume-one", timeout=5, states={"destroyed"}, ok_statuses=[404])

        self.assertEqual(get.call_count, 2)
        self.assertIsNone(result)

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

    def test_volume_wait_keeps_request_slack_when_timeout_is_exhausted(self):
        volume = {"id": "volume-one", "state": "creating"}
        with (
            patch(f"{FLYIO_UTILS}.time.monotonic", side_effect=[10, 10, 10]),
            patch(f"{FLYIO_UTILS}.get_resource", return_value=volume) as get,
            patch(f"{FLYIO_UTILS}.time.sleep"),
        ):
            result = wait_for_volume({}, "example", "volume-one", timeout=0)

        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["timeout"], 11)
        self.assertEqual(result, volume)

    def test_wait_polls_at_least_once_when_timeout_is_exhausted(self):
        app = {"name": "example"}
        with (
            patch(f"{FLYIO_UTILS}.time.monotonic", side_effect=[10, 10, 10]),
            patch(f"{FLYIO_UTILS}.get_resource", return_value=app) as get,
            patch(f"{FLYIO_UTILS}.time.sleep") as sleep,
        ):
            result = wait_for_app_absent({}, "example", timeout=0)

        get.assert_called_once()
        # The final poll keeps request slack even when the wait budget is spent.
        self.assertEqual(get.call_args.kwargs["timeout"], 11)
        sleep.assert_not_called()
        self.assertEqual(result, app)

    def test_client_accepts_token_with_trailing_newline(self):
        module = Mock(params={"api_token": "abc123\n"})

        with flyio_client(module) as client:
            pass

        module.fail_json.assert_not_called()
        self.assertEqual(client["headers"]["Authorization"], "Bearer abc123")

    def test_graphql_not_found_uses_error_code(self):
        exc = FlyioApiError("failed", response_body=[{"message": "nope", "extensions": {"code": "NOT_FOUND"}}])
        self.assertTrue(graphql_not_found(exc))
        self.assertFalse(graphql_not_found(FlyioApiError("failed", response_body=[{"message": "denied"}])))

    def test_incomplete_response_raises_api_error(self):
        response = Mock()
        response.read.side_effect = http.client.IncompleteRead(b"")
        with (
            patch(f"{FLYIO_UTILS}.open_url", return_value=response),
            self.assertRaises(FlyioApiError),
        ):
            api_request({"headers": {}}, "get", "/apps/example")

    def test_volume_wait_stops_on_failed_state(self):
        failed = {"id": "volume-one", "state": "failed"}
        with (
            patch(f"{FLYIO_UTILS}.time.monotonic", return_value=0),
            patch(f"{FLYIO_UTILS}.get_resource", return_value=failed) as get,
            patch(f"{FLYIO_UTILS}.time.sleep") as sleep,
        ):
            result = wait_for_volume({}, "example", "volume-one", timeout=60)

        get.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(result, failed)

    def test_machine_wait_asks_once_when_budget_is_spent(self):
        with patch(f"{FLYIO_UTILS}.api_request", return_value={"ok": True}) as request:
            wait_for_machine({}, "example", "machine-one", "started", 0)

        request.assert_called_once()
        self.assertIn("timeout=1", request.call_args.args[2])

    def test_get_app_tolerates_missing_app(self):
        with patch(f"{FLYIO_UTILS}.get_resource", return_value=None) as get:
            self.assertIsNone(get_app({}, "example", timeout=5))

        get.assert_called_once_with(
            {},
            "/apps/example",
            ok_statuses=[404],
            timeout=5,
            required_fields=("name",),
            expected={"name": "example"},
        )

    def test_truncated_error_body_keeps_api_error_and_status(self):
        error = HTTPError("https://api.machines.dev/v1/apps/example", 503, "Service Unavailable", {}, None)
        error.read = Mock(side_effect=http.client.IncompleteRead(b""))
        with (
            patch(f"{FLYIO_UTILS}.open_url", side_effect=error),
            self.assertRaises(FlyioApiError) as raised,
        ):
            api_request({"headers": {}}, "get", "/apps/example")

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIsNone(raised.exception.response_body)

    def test_authorization_header_recognises_all_macaroon_prefixes(self):
        for token in ("fm1a_abc", "fm1r_abc", "fm2_abc", "fo1_x, fm2_abc"):
            with self.subTest(token=token):
                self.assertEqual(authorization_header(token), f"FlyV1 {token}")

        self.assertEqual(authorization_header("fo1_abc"), "Bearer fo1_abc")
