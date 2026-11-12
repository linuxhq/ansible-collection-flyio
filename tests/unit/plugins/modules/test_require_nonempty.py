# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import (
    apps,
    apps_info,
    ip_addresses,
    ip_addresses_info,
    machines,
    machines_exec,
    machines_info,
    secrets,
    secrets_info,
    volumes,
    volumes_info,
)
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleFail,
)

# Each module's identifier options that must reject blank strings before any API call.
NONEMPTY_OPTIONS = {
    apps: ("name", "org_slug", "network"),
    apps_info: ("name", "org_slug"),
    ip_addresses: ("app_name", "address"),
    ip_addresses_info: ("app_name",),
    machines: ("app_name", "id", "name"),
    machines_exec: ("app_name", "id", "command", "container"),
    machines_info: ("app_name", "id"),
    secrets: ("app_name", "name"),
    secrets_info: ("app_name",),
    volumes: ("app_name", "id", "name"),
    volumes_info: ("app_name", "id"),
}


class RequireNonemptyTests(TestCase):
    def test_modules_reject_blank_identifiers_before_api_calls(self):
        for module_under_test, names in NONEMPTY_OPTIONS.items():
            for name in names:
                with (
                    self.subTest(module=module_under_test.__name__, option=name),
                    patch.object(module_under_test, "AnsibleModule", return_value=FakeModule({name: " "})),
                    patch.object(module_under_test, "flyio_client") as client,
                    self.assertRaises(ModuleFail) as raised,
                ):
                    module_under_test.main()

                client.assert_not_called()
                self.assertEqual(raised.exception.values["msg"], f"{name} must not be empty")
