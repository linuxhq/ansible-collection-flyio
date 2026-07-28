# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


import json
import time
import urllib.error
from contextlib import contextmanager

from ansible.module_utils.urls import open_url

GRAPHQL_API_URL = "https://api.fly.io/graphql"
MACHINES_API_URL = "https://api.machines.dev/v1"


@contextmanager
def flyio_client(module):
    token = module.params.get("api_token")
    if not token:
        module.fail_json(msg="api_token is required")

    client = {
        "token": token,
        "headers": {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    }

    try:
        yield client
    except FlyioApiError as exc:
        fail_from_flyio_error(module, str(exc), exc)


class FlyioApiError(Exception):
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def api_request(client, method, path, body=None, ok_statuses=None):
    ok_statuses = ok_statuses or []
    url = f"{MACHINES_API_URL}{path}"
    data = json.dumps(body) if body is not None else None

    try:
        response = open_url(
            url,
            method=method.upper(),
            data=data,
            headers=client["headers"],
        )
        content = response.read()
        if content:
            return json.loads(content)
        return None
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        if status_code in ok_statuses:
            return None

        response_body = None
        try:
            response_body = json.loads(exc.read())
        except (ValueError, AttributeError):
            response_body = None

        raise FlyioApiError(
            str(exc),
            status_code=status_code,
            response_body=response_body,
        )
    except urllib.error.URLError as exc:
        raise FlyioApiError(str(exc))
    except ValueError as exc:
        raise FlyioApiError(f"Invalid JSON in API response: {exc}")


def delete_result(client, path):
    return api_request(client, "delete", path)


def get_ip_addresses(client, app_name):
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
                        createdAt
                    }
                }
            }
        }
    """
    data = graphql_request(client, query, {"appName": app_name})
    app = data.get("app") or {}
    addresses = list(app.get("ipAddresses", {}).get("nodes", []))

    shared = app.get("sharedIpAddress")
    if shared:
        addresses.append({"address": shared, "type": "shared_v4", "region": ""})

    return addresses


def graphql_request(client, query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        response = open_url(
            GRAPHQL_API_URL,
            method="POST",
            data=json.dumps(payload),
            headers=client["headers"],
        )
        result = json.loads(response.read())
    except (urllib.error.URLError, ValueError) as exc:
        raise FlyioApiError(str(exc))

    if result.get("errors"):
        raise FlyioApiError(result["errors"][0].get("message", "GraphQL error"))

    return result.get("data", {})


def fail_from_flyio_error(module, message, exc):
    status_code = getattr(exc, "status_code", None)
    response_body = getattr(exc, "response_body", None)

    module.fail_json(
        msg=message,
        error=str(exc),
        status_code=status_code,
        response=response_body,
    )


def get_result(client, path, default=None, ok_statuses=None):
    result = api_request(client, "get", path, ok_statuses=ok_statuses)
    if result is None:
        return default
    return result


def list_all(client, path):
    result = api_request(client, "get", path)
    if result is None:
        return []
    if isinstance(result, list):
        return result
    return [result]


def patch_result(client, path, body):
    return api_request(client, "patch", path, body=body)


def post_result(client, path, body):
    return api_request(client, "post", path, body=body)


def put_result(client, path, body):
    return api_request(client, "put", path, body=body)


def select_fields(value, fields):
    if not isinstance(value, dict):
        return {}
    return {field: value.get(field) for field in fields if field in value}


def values_differ(current, desired):
    if not isinstance(current, dict) or not isinstance(desired, dict):
        return current != desired

    if not desired:
        return bool(current)

    for key, value in desired.items():
        if key not in current:
            return True
        cur = current[key]
        if isinstance(value, dict) and isinstance(cur, dict):
            if values_differ(cur, value):
                return True
        elif isinstance(value, list) and isinstance(cur, list):
            if len(value) != len(cur):
                return True
            for c, d in zip(cur, value):
                if values_differ(c, d):
                    return True
        elif cur != value:
            return True
    return False


def wait_for_machine(client, app_name, machine_id, state="started", timeout=60):
    path = (
        f"/apps/{app_name}/machines/{machine_id}/wait?state={state}&timeout={timeout}"
    )
    api_request(client, "get", path)


def wait_for_volume(client, app_name, volume_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        volume = get_result(
            client,
            f"/apps/{app_name}/volumes/{volume_id}",
        )
        if volume and volume.get("state") == "created":
            return volume

        time.sleep(2)

    return get_result(
        client,
        f"/apps/{app_name}/volumes/{volume_id}",
    )
