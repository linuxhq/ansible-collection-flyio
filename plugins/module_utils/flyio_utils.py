# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


import http.client
import ipaddress
import json
import math
import time
import urllib.error
import urllib.parse
from contextlib import contextmanager

from ansible.module_utils.common.parameters import env_fallback
from ansible.module_utils.urls import ConnectionError as AnsibleConnectionError
from ansible.module_utils.urls import open_url

GRAPHQL_API_URL = "https://api.fly.io/graphql"
MACHINES_API_URL = "https://api.machines.dev/v1"
_MISSING = object()
# Machines in these states are gone.
MACHINE_TERMINAL_STATES = {"destroyed", "replaced", "migrated"}
# IP address fields requested from GraphQL, in the snake_case form the modules return.
IP_ADDRESS_FIELDS = """
    id
    address
    type
    region
    created_at: createdAt
    network {
        name
    }
    service_name: serviceName
"""
# Region groups accepted by Fly.io create requests; Fly.io picks the actual region.
REGION_GROUPS = {
    "africa",
    "any",
    "apac",
    "asia_pacific",
    "eu",
    "europe",
    "na",
    "north_america",
    "sa",
    "south_america",
    "us",
}


def api_token_option():
    """Argument spec for O(api_token), documented by the linuxhq.flyio.api fragment."""
    return {"type": "str", "no_log": True, "fallback": (env_fallback, ["FLY_API_TOKEN"])}


def authorization_header(token):
    if token.startswith(("Bearer ", "FlyV1 ")):
        return token

    # Same macaroon prefixes as Fly.io's fly-go client, which sends these with the FlyV1 scheme.
    if any(part.strip().partition("_")[0] in ("fm1r", "fm1a", "fm2") for part in token.split(",")):
        return f"FlyV1 {token}"

    return f"Bearer {token}"


def flyio_path(*parts):
    return "/" + "/".join(urllib.parse.quote(part, safe="") for part in parts)


@contextmanager
def flyio_client(module):
    token = module.params.get("api_token")
    if not isinstance(token, str) or not token.strip():
        module.fail_json(msg="api_token is required; set api_token or FLY_API_TOKEN")

    # Strip first so surrounding whitespace, such as a trailing newline from a file, is tolerated.
    token = token.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in token):
        module.fail_json(msg="api_token must not contain control characters")

    client = {
        "headers": {
            "Authorization": authorization_header(token),
            "Content-Type": "application/json",
        },
    }

    try:
        yield client
    except FlyioApiError as exc:
        if exc.write_sent:
            mark_changed(module)

        module.fail_json(msg=str(exc), **api_error_result(exc))


def api_error_result(exc):
    """Result fields describing a Fly.io API error."""
    return {"error": str(exc), "status_code": exc.status_code, "response": exc.response_body}


def fail_rejected_request(module, action, errors, **result):
    """In check mode, fail as the real run would when Fly.io is known to reject the request."""
    module.fail_json(msg=f"Fly.io would reject the request to {action}: " + "; ".join(errors), **result)


def mark_changed(module):
    """Report changed=True on every later failure; call once a write has been sent."""
    fail_json = module.fail_json

    def fail_changed(**kwargs):
        fail_json(**{"changed": True, **kwargs})

    module.fail_json = fail_changed


class FlyioApiError(Exception):
    def __init__(self, message, status_code=None, response_body=None, write_sent=False):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        # A write reached Fly.io but its response was lost, so it may have been applied.
        self.write_sent = write_sent


def _error_response(exc):
    try:
        content = exc.read()
    except (AttributeError, OSError, http.client.HTTPException):
        return None

    if not content:
        return None

    try:
        return json.loads(content)
    except ValueError:
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")

        return str(content)


def _error_reason(response_body):
    """Return Fly.io's reason from an error response: its error message or plain-text body."""
    if isinstance(response_body, dict) and isinstance(response_body.get("error"), str):
        return response_body["error"].strip()

    if isinstance(response_body, str):
        return response_body.strip()

    return ""


def _send(client, method, url, body, timeout, operation, ok_statuses=(), write=False):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    try:
        response = open_url(
            url,
            method=method,
            data=data,
            headers=client["headers"],
            timeout=timeout,
        )
    except urllib.error.HTTPError as exc:
        if exc.code in ok_statuses:
            return _MISSING

        response_body = _error_response(exc)
        reason = _error_reason(response_body)
        raise FlyioApiError(
            f"{operation} failed: {exc}" + (f": {reason}" if reason else ""),
            status_code=exc.code,
            response_body=response_body,
        ) from exc
    except (urllib.error.URLError, AnsibleConnectionError, ValueError) as exc:
        # urllib wraps only failures raised before the request was sent; ValueError rejects the request itself.
        raise FlyioApiError(f"{operation} failed: {exc}") from exc
    except (OSError, http.client.HTTPException) as exc:
        # Raised while waiting for the response, after the request was sent.
        raise FlyioApiError(f"{operation} failed: {exc}", write_sent=write) from exc

    try:
        content = response.read()
        return json.loads(content) if content else None
    except (OSError, http.client.HTTPException) as exc:
        raise FlyioApiError(f"{operation} failed: {exc}", write_sent=write) from exc
    except ValueError as exc:
        raise FlyioApiError(f"{operation} returned invalid JSON: {exc}", write_sent=write) from exc


def api_request(client, method, path, body=None, ok_statuses=None, timeout=30):
    return _send(
        client,
        method.upper(),
        f"{MACHINES_API_URL}{path}",
        body,
        timeout,
        f"{method.upper()} {path}",
        ok_statuses or (),
        write=method.upper() != "GET",
    )


def delete_result(client, path, timeout=30):
    return api_request(client, "delete", path, timeout=timeout)


def blank(value):
    return isinstance(value, str) and not value.strip()


def ip_version(value):
    if not isinstance(value, str) or "%" in value:
        return None

    try:
        return ipaddress.ip_address(value).version
    except ValueError:
        return None


def shared_ip_address(address):
    """Represent an app's shared IPv4 address like an allocated address."""
    return {"address": address, "type": "shared_v4", "region": ""}


def get_ip_addresses(client, app_name, missing_ok=False):
    operation = f"List IP addresses for app '{app_name}'"
    query = (
        """
        query($appName: String!) {
            app(name: $appName) {
                sharedIpAddress
                ipAddresses {
                    nodes {"""
        + IP_ADDRESS_FIELDS
        + """}
                }
            }
        }
    """
    )
    try:
        data = graphql_request(
            client,
            query,
            {"appName": app_name},
            operation=operation,
        )
    except FlyioApiError as exc:
        if missing_ok and graphql_not_found(exc):
            return []

        raise

    app = data["app"]
    if app is None:
        if missing_ok:
            return []

        raise FlyioApiError(f"App '{app_name}' not found")

    addresses = app["ipAddresses"]["nodes"]
    if app["sharedIpAddress"] is not None:
        addresses.append(shared_ip_address(app["sharedIpAddress"]))

    return addresses


def graphql_not_found(exc):
    errors = exc.response_body if isinstance(exc.response_body, list) else []
    return (
        any(
            isinstance(error, dict)
            and isinstance(error.get("extensions"), dict)
            and error["extensions"].get("code") == "NOT_FOUND"
            for error in errors
        )
        or "could not find app" in str(exc).lower()
    )


def graphql_request(client, query, variables=None, operation="GraphQL request", mutation=False):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    result = _send(client, "POST", GRAPHQL_API_URL, payload, 30, operation, write=mutation)
    if result.get("errors"):
        errors = result["errors"]
        raise FlyioApiError(
            f"{operation} failed: {errors[0]['message']}",
            response_body=errors,
        )

    return result["data"]


def get_resource(client, path, ok_statuses=None, timeout=30, expected=None):
    """Get one resource; with expected, fail unless the response is the resource whose fields match it."""
    result = api_request(client, "get", path, ok_statuses=ok_statuses, timeout=timeout)
    if result is _MISSING:
        return None

    # flyio_path leaves "." and ".." unquoted, so such an identifier can reach a different route.
    if expected and (
        not isinstance(result, dict) or any(result.get(field) != value for field, value in expected.items())
    ):
        fields = ", ".join(f"{field}={value!r}" for field, value in expected.items())
        raise FlyioApiError(f"GET {path} returned a different resource: expected {fields}")

    return result


def list_all(client, path, ok_statuses=None):
    result = api_request(client, "get", path, ok_statuses=ok_statuses)
    return [] if result is _MISSING else result


def post_result(client, path, body=None, timeout=30):
    return api_request(client, "post", path, body=body, timeout=timeout)


def diff_result(module, before, after):
    """Return the diff entry for a changed result when diff mode is enabled."""
    return {"diff": {"before": before, "after": after}} if module._diff else {}


def select_fields(value, fields):
    return {field: value.get(field) for field in fields if field in value}


def require_region_code(module):
    """Fail unless O(region) is unset or a single region code, and normalise it to the lowercase code Fly.io reports."""
    region = module.params.get("region")
    if region is None:
        return

    region = region.strip().lower()
    if not region:
        module.fail_json(msg="region must not be empty")

    if "," in region or region in REGION_GROUPS:
        module.fail_json(msg="region must be a single region code; region lists and groups are not supported")

    module.params["region"] = region


def require_nonempty(module, *names):
    """Fail when any named string option is set but blank; unset options are left to the argument spec."""
    for name in names:
        if blank(module.params.get(name)):
            module.fail_json(msg=f"{name} must not be empty")


def require_positive(module, *names):
    for name in names:
        value = module.params[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            module.fail_json(msg=f"{name} must be greater than zero")


def wait_for_machine(client, app_name, machine_id, state="started", timeout=60, version=None):
    operation = f"Wait for Machine '{machine_id}' in app '{app_name}' to reach state '{state}'"
    ok_statuses = [404] if state == "destroyed" else None
    deadline = wait_deadline(timeout)
    remaining = timeout
    while True:
        # Always ask at least once, even when the time budget is already spent.
        request_timeout = max(1, min(60, math.ceil(remaining)))
        query = {"state": state, "timeout": request_timeout}
        if version is not None:
            query["version"] = version

        path = f"{flyio_path('apps', app_name, 'machines', machine_id, 'wait')}?{urllib.parse.urlencode(query)}"
        try:
            api_request(
                client,
                "get",
                path,
                ok_statuses=ok_statuses,
                timeout=request_timeout + 10,
            )
            return
        except FlyioApiError as exc:
            if exc.status_code != 408:
                raise

            remaining = seconds_left(deadline)
            if remaining <= 0:
                raise FlyioApiError(f"{operation} timed out", status_code=408) from exc


def wait_deadline(timeout):
    return time.monotonic() + timeout


def seconds_left(deadline):
    return max(0, deadline - time.monotonic())


def poll_until(fetch, done, timeout):
    """Fetch at least once, then poll until done or timeout; return the last value.

    Each fetch gets the remaining time plus slack as its request timeout, so a slow
    final poll returns the last value instead of failing the request.
    """
    deadline = wait_deadline(timeout)
    while True:
        value = fetch(max(1, seconds_left(deadline)) + 10)
        if done(value) or time.monotonic() >= deadline:
            return value

        time.sleep(min(2, seconds_left(deadline)))


def get_app(client, app_name, timeout=30):
    return get_resource(
        client,
        flyio_path("apps", app_name),
        ok_statuses=[404],
        timeout=timeout,
        expected={"name": app_name},
    )


def get_machine(client, app_name, machine_id):
    return get_resource(
        client,
        flyio_path("apps", app_name, "machines", machine_id),
        ok_statuses=[404],
        expected={"id": machine_id},
    )


def get_volume(client, app_name, volume_id, ok_statuses=(404,), timeout=30):
    return get_resource(
        client,
        flyio_path("apps", app_name, "volumes", volume_id),
        ok_statuses=ok_statuses,
        timeout=timeout,
        expected={"id": volume_id},
    )


def wait_for_app_absent(client, app_name, timeout=60):
    return poll_until(
        lambda request_timeout: get_app(client, app_name, request_timeout), lambda app: app is None, timeout
    )


def wait_for_volume(
    client,
    app_name,
    volume_id,
    timeout=60,
    states=("created",),
    ok_statuses=None,
    size_gb=None,
    stop_states=(),
):
    """Poll until the volume reaches one of states, fails, or enters one of stop_states."""

    def fetch(request_timeout):
        return get_volume(client, app_name, volume_id, ok_statuses=ok_statuses, timeout=request_timeout)

    def done(volume):
        # A failed or stopping volume will not reach the target, so stop waiting and let the caller report it.
        if volume is None or volume["state"] == "failed" or volume["state"] in stop_states:
            return True

        if volume["state"] not in states:
            return False

        return size_gb is None or volume["size_gb"] >= size_gb

    return poll_until(fetch, done, timeout)
