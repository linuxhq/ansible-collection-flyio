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
        machine = {"id": "machine-one"}
        module = FakeModule({"app_name": "example", "id": "machine-one"})

        with (
            patch.object(machines_info, "get_result", return_value=machine),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines_info.info(module, {})

        self.assertEqual(raised.exception.values["machines"], [machine])

    def test_missing_machine_fails(self):
        module = FakeModule({"app_name": "example", "id": "missing"})

        with (
            patch.object(machines_info, "get_result", return_value=None),
            self.assertRaises(ModuleFail),
        ):
            machines_info.info(module, {})

    def test_wraps_single_list_result(self):
        machine = {"id": "machine-one"}
        module = FakeModule({"app_name": "example"})

        with (
            patch.object(machines_info, "get_result", return_value=machine),
            self.assertRaises(ModuleExit) as raised,
        ):
            machines_info.list_resources(module, {})

        self.assertEqual(raised.exception.values["machines"], [machine])
