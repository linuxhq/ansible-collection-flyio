# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import volumes_info
from ansible_collections.linuxhq.flyio.tests.unit.plugins.modules.utils import (
    FakeModule,
    ModuleExit,
    ModuleFail,
)


class VolumesInfoTests(TestCase):
    def test_info(self):
        volume = {"id": "vol_one"}
        module = FakeModule({"app_name": "example", "id": "vol_one"})

        with (
            patch.object(volumes_info, "get_result", return_value=volume) as get,
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes_info.info(module, {})

        get.assert_called_once_with(
            {}, "/apps/example/volumes/vol_one", ok_statuses=[404]
        )
        self.assertEqual(raised.exception.values["volumes"], [volume])

    def test_missing_volume_fails(self):
        module = FakeModule({"app_name": "example", "id": "missing"})

        with (
            patch.object(volumes_info, "get_result", return_value=None),
            self.assertRaises(ModuleFail),
        ):
            volumes_info.info(module, {})

    def test_lists_volumes(self):
        volumes = [{"id": "one"}, {"id": "two"}]
        module = FakeModule({"app_name": "example"})

        with (
            patch.object(volumes_info, "get_result", return_value=volumes),
            self.assertRaises(ModuleExit) as raised,
        ):
            volumes_info.list_resources(module, {})

        self.assertEqual(raised.exception.values["volumes"], volumes)
