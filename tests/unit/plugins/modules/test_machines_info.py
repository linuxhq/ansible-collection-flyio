# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import machines_info
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


class MachinesInfoTests(TestCase):
    def test_info(self):
        machine = {
            "config": {
                "env": {"TOKEN": "secret"},
                "files": [{"guest_path": "/secret", "raw_value": "c2VjcmV0"}],
            },
            "id": "machine-one",
        }
        module = FakeModule({"app_name": "example", "id": "machine-one"})

        with (
            patch.object(machines_info, "get_resource", return_value=machine) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines_info.info(module, {})

        get.assert_called_once_with(
            {},
            "/apps/example/machines/machine-one",
            ok_statuses=[404],
            required_fields=("id",),
            expected={"id": "machine-one"},
        )
        self.assertEqual(raised.exception.values["machines"], [machine])

    def test_missing_machine_fails(self):
        module = FakeModule({"app_name": "example", "id": "missing"})

        with (
            patch.object(machines_info, "get_resource", return_value=None),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_info.info(module, {})

        self.assertEqual(
            raised.exception.values["msg"],
            "Machine 'missing' not found in app 'example'",
        )

    def test_lists_machines(self):
        machine = {"id": "machine-one"}
        module = FakeModule({"app_name": "example"})

        with (
            patch.object(machines_info, "list_all", return_value=[machine]) as list_all,
            self.assertRaises(ModuleExit) as raised,
        ):
            machines_info.list_resources(module, {})

        list_all.assert_called_once_with({}, "/apps/example/machines", ok_statuses=[404])
        self.assertEqual(raised.exception.values["machines"], [machine])

    def test_rejects_malformed_documented_fields(self):
        module = FakeModule({"app_name": "example"})

        with (
            patch.object(
                machines_info,
                "list_all",
                return_value=[{"id": "machine-one", "state": False}],
            ),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_info.list_resources(module, {})

        self.assertIn("malformed Machine data", raised.exception.values["msg"])

    def test_listing_without_ids_reports_app_specific_failure(self):
        module = FakeModule({"app_name": "example"})

        with (
            patch(
                "ansible_collections.linuxhq.flyio.plugins.module_utils.flyio_utils.api_request",
                return_value=[{"state": "started"}],
            ),
            self.assertRaises(ModuleFail) as raised,
        ):
            machines_info.list_resources(module, {})

        self.assertEqual(raised.exception.values["msg"], "Fly.io API returned malformed Machine data for app 'example'")
