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

from ansible.module_utils.urls import ConnectionError as AnsibleConnectionError
from ansible.module_utils.urls import open_url

GRAPHQL_API_URL = "https://api.fly.io/graphql"
MACHINES_API_URL = "https://api.machines.dev/v1"
_MISSING = object()
SECRET_FIELDS = ("name", "digest", "created_at", "updated_at")
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
        module.fail_json(msg="api_token is required")

    # Strip first so surrounding whitespace, such as a trailing newline from a file, is tolerated.
    token = token.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in token):
        module.fail_json(msg="api_token must not contain control characters")

    if token in ("Bearer", "FlyV1"):
        module.fail_json(msg="api_token credential must not be empty")

    for name in ("address", "app_name", "id", "name", "network", "org_slug"):
        value = module.params.get(name)
        if isinstance(value, str) and not value.strip():
            module.fail_json(msg=f"{name} must not be empty")

    client = {
        "headers": {
            "Authorization": authorization_header(token),
            "Content-Type": "application/json",
        },
    }

    try:
        yield client
    except FlyioApiError as exc:
        module.fail_json(
            msg=str(exc),
            error=str(exc),
            status_code=exc.status_code,
            response=exc.response_body,
        )


class FlyioApiError(Exception):
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


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


def _send(client, method, url, body, timeout, operation, ok_statuses=()):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    try:
        response = open_url(
            url,
            method=method,
            data=data,
            headers=client["headers"],
            timeout=timeout,
        )
        content = response.read()
        return json.loads(content) if content else None
    except urllib.error.HTTPError as exc:
        if exc.code in ok_statuses:
            return _MISSING

        raise FlyioApiError(
            f"{operation} failed: {exc}",
            status_code=exc.code,
            response_body=_error_response(exc),
        ) from exc
    except (OSError, http.client.HTTPException, AnsibleConnectionError) as exc:
        raise FlyioApiError(f"{operation} failed: {exc}") from exc
    except ValueError as exc:
        raise FlyioApiError(f"{operation} returned invalid JSON: {exc}") from exc


def api_request(client, method, path, body=None, ok_statuses=None, timeout=30):
    return _send(
        client,
        method.upper(),
        f"{MACHINES_API_URL}{path}",
        body,
        timeout,
        f"{method.upper()} {path}",
        ok_statuses or (),
    )


def delete_result(client, path, timeout=30, ok_statuses=None):
    result = api_request(
        client,
        "delete",
        path,
        ok_statuses=ok_statuses,
        timeout=timeout,
    )
    return None if result is _MISSING else result


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def optional_strings(value, fields):
    return all(field not in value or nonempty_string(value[field]) for field in fields)


def valid_machine(machine):
    return (
        isinstance(machine, dict)
        and nonempty_string(machine.get("id"))
        and optional_strings(machine, ("name", "region", "state"))
    )


def valid_volume(volume):
    return (
        isinstance(volume, dict)
        and nonempty_string(volume.get("id"))
        and optional_strings(volume, ("name", "region", "state"))
        and ("size_gb" not in volume or positive_int(volume["size_gb"]))
        and ("encrypted" not in volume or isinstance(volume["encrypted"], bool))
    )


def valid_secret_metadata(secret):
    return (
        isinstance(secret, dict)
        and nonempty_string(secret.get("name"))
        and nonempty_string(secret.get("digest"))
        and optional_strings(secret, ("created_at", "updated_at"))
    )


def ip_version(value):
    if not isinstance(value, str) or "%" in value:
        return None

    try:
        return ipaddress.ip_address(value).version
    except ValueError:
        return None


def valid_ip_address(address):
    if not isinstance(address, dict):
        return False

    address_version = ip_version(address.get("address"))
    address_type = address.get("type")
    if not isinstance(address_type, str):
        return False

    expected_version = {
        "private_v6": 6,
        "shared_v4": 4,
        "v4": 4,
        "v6": 6,
    }.get(address_type)
    return (
        expected_version is not None
        and address_version == expected_version
        and all(address.get(field) is None or nonempty_string(address[field]) for field in ("id", "created_at"))
        and (address.get("region") is None or (isinstance(address["region"], str) and not address["region"].isspace()))
    )


def normalize_ip_address(address):
    return {
        field: "" if field == "region" and value == "global" else value
        for field, value in address.items()
        if value is not None
    }


def get_ip_addresses(client, app_name, missing_ok=False):
    operation = f"List IP addresses for app '{app_name}'"
    query = """
        query($appName: String!) {
            app(name: $appName) {
                sharedIpAddress
                ipAddresses {
                    nodes {
                        id
                        address
                        type
                        region
                        created_at: createdAt
                    }
                }
            }
        }
    """
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

    app = data.get("app")
    if app is None:
        if missing_ok:
            return []

        raise FlyioApiError(f"App '{app_name}' not found")

    if not isinstance(app, dict):
        raise FlyioApiError(f"{operation} returned malformed data: expected an app")

    ip_addresses = app.get("ipAddresses")
    if not isinstance(ip_addresses, dict):
        raise FlyioApiError(f"{operation} returned malformed data: expected an address connection")

    addresses = ip_addresses.get("nodes")
    if not isinstance(addresses, list) or not all(valid_ip_address(address) for address in addresses):
        raise FlyioApiError(f"{operation} returned malformed data: expected a list")

    addresses = [normalize_ip_address(address) for address in addresses]

    shared = app.get("sharedIpAddress")
    if shared is not None:
        shared_address = {"address": shared, "type": "shared_v4", "region": ""}
        if not valid_ip_address(shared_address):
            raise FlyioApiError(f"{operation} returned malformed data: expected a shared address")

        addresses.append(shared_address)

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


def graphql_request(client, query, variables=None, timeout=30, operation="GraphQL request"):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    result = _send(client, "POST", GRAPHQL_API_URL, payload, timeout, operation)

    if not isinstance(result, dict):
        raise FlyioApiError(f"{operation} returned malformed data: expected an object")

    if result.get("errors"):
        errors = result["errors"]
        message = (
            errors[0].get("message", "GraphQL error")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict)
            else "GraphQL error"
        )
        raise FlyioApiError(
            f"{operation} failed: {message}",
            response_body=errors,
        )

    data = result.get("data")
    if not isinstance(data, dict):
        raise FlyioApiError(f"{operation} returned malformed data: expected a data object")

    return data


def get_result(client, path, default=None, ok_statuses=None, timeout=30):
    result = api_request(client, "get", path, ok_statuses=ok_statuses, timeout=timeout)
    if result is _MISSING:
        return default

    return result


def _valid_resource(value, required_fields):
    return isinstance(value, dict) and all(nonempty_string(value.get(field)) for field in required_fields)


def get_resource(client, path, ok_statuses=None, timeout=30, required_fields=(), expected=None):
    """Get one resource whose required string fields are present and whose expected fields match."""
    result = api_request(client, "get", path, ok_statuses=ok_statuses, timeout=timeout)
    if result is _MISSING:
        return None

    if not _valid_resource(result, required_fields) or any(
        result.get(field) != value for field, value in (expected or {}).items()
    ):
        raise FlyioApiError(f"GET {path} returned malformed data: expected an object")

    return result


def list_all(client, path, ok_statuses=None, required_fields=()):
    result = api_request(client, "get", path, ok_statuses=ok_statuses)
    if result is _MISSING:
        return []

    if not isinstance(result, list) or not all(_valid_resource(item, required_fields) for item in result):
        raise FlyioApiError(f"GET {path} returned malformed data: expected a list")

    return result


def post_result(client, path, body=None, timeout=30):
    return api_request(client, "post", path, body=body, timeout=timeout)


def put_result(client, path, body):
    return api_request(client, "put", path, body=body)


def select_fields(value, fields):
    return {field: value.get(field) for field in fields if field in value}


def sanitize_machine(machine):
    if machine is None:
        return None

    if not isinstance(machine, dict):
        return {}

    def sanitize_config(value):
        if isinstance(value, list):
            return [sanitize_config(item) for item in value]

        if not isinstance(value, dict):
            return value

        result = {}
        for key, item in value.items():
            if key in ("env", "headers", "raw_value"):
                continue

            if key == "metadata":
                # Metadata keys are caller-chosen names, not configuration fields.
                result[key] = item
            elif key == "checks" and isinstance(item, dict):
                # Check names are caller-chosen; sanitize each check, not the names.
                result[key] = {name: sanitize_config(check) for name, check in item.items()}
            else:
                result[key] = sanitize_config(item)

        return result

    result = sanitize_config(machine)
    for field in ("config", "incomplete_config"):
        if field in result and not isinstance(result[field], dict):
            del result[field]

    return result


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


def require_positive(module, *names):
    for name in names:
        if not positive_int(module.params[name]):
            module.fail_json(msg=f"{name} must be greater than zero")


def wait_for_machine(client, app_name, machine_id, state="started", timeout=60, version=None):
    operation = f"Wait for Machine '{machine_id}' in app '{app_name}' to reach state '{state}'"
    if version is not None and not nonempty_string(version):
        raise FlyioApiError(f"{operation} received a malformed version")

    if state == "stopped" and version is None:
        raise FlyioApiError(f"{operation} requires a version")

    ok_statuses = [404] if state == "destroyed" else None
    deadline = time.monotonic() + timeout
    remaining = timeout
    while True:
        # Always ask at least once, even when the time budget is already spent.
        request_timeout = max(1, min(60, math.ceil(remaining)))
        query = {"state": state, "timeout": request_timeout}
        if version is not None:
            query["version"] = version

        path = f"{flyio_path('apps', app_name, 'machines', machine_id, 'wait')}?{urllib.parse.urlencode(query)}"
        try:
            result = api_request(
                client,
                "get",
                path,
                ok_statuses=ok_statuses,
                timeout=request_timeout + 10,
            )
            break
        except FlyioApiError as exc:
            if exc.status_code != 408:
                raise

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FlyioApiError(f"{operation} timed out", status_code=408) from exc

    if result is _MISSING and state == "destroyed":
        return

    if not isinstance(result, dict) or result.get("ok") is not True:
        raise FlyioApiError(f"{operation} returned malformed data: expected ok=true")


def wait_deadline(timeout):
    return time.monotonic() + timeout


def seconds_left(deadline):
    return max(0, deadline - time.monotonic())


def poll_until(fetch, done, timeout):
    """Fetch at least once, then poll until done or timeout; return the last value."""
    deadline = time.monotonic() + timeout
    while True:
        value = fetch(max(1, deadline - time.monotonic()))
        if done(value) or time.monotonic() >= deadline:
            return value

        time.sleep(min(2, max(0, deadline - time.monotonic())))


def get_app(client, app_name, timeout=30):
    return get_resource(
        client,
        flyio_path("apps", app_name),
        ok_statuses=[404],
        timeout=timeout,
        required_fields=("name",),
        expected={"name": app_name},
    )


def wait_for_app_absent(client, app_name, timeout=60):
    return poll_until(lambda remaining: get_app(client, app_name, remaining), lambda app: app is None, timeout)


def wait_for_volume(
    client,
    app_name,
    volume_id,
    timeout=60,
    states=("created",),
    ok_statuses=None,
    size_gb=None,
):
    operation = f"Wait for volume '{volume_id}' in app '{app_name}'"

    def fetch(remaining):
        volume = get_resource(
            client,
            flyio_path("apps", app_name, "volumes", volume_id),
            ok_statuses=ok_statuses,
            timeout=remaining,
            required_fields=("id", "state"),
            expected={"id": volume_id},
        )
        if volume is not None and not valid_volume(volume):
            raise FlyioApiError(f"{operation} returned malformed data")

        return volume

    def done(volume):
        # A failed volume will not recover, so stop waiting and let the caller report it.
        if volume is None or volume["state"] == "failed":
            return True

        if volume["state"] not in states:
            return False

        if size_gb is None:
            return True

        current_size = volume.get("size_gb")
        if not positive_int(current_size):
            raise FlyioApiError(f"{operation} returned malformed data: expected an integer size")

        return current_size >= size_gb

    return poll_until(fetch, done, timeout)
