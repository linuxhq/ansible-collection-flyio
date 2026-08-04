# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from unittest import TestCase
from unittest.mock import patch

from ansible_collections.linuxhq.flyio.plugins.modules import volumes


class FindVolumeTests(TestCase):
    def test_skips_pending_destroy(self):
        pending = {
            "id": "vol_old",
            "name": "data",
            "region": "ord",
            "state": "pending_destroy",
        }
        created = {
            "id": "vol_new",
            "name": "data",
            "region": "ord",
            "state": "created",
        }

        with patch.object(volumes, "list_all", return_value=[pending, created]):
            result = volumes.find_volume({}, "example", name="data", region="ord")

        self.assertEqual(result, created)

    def test_destroyed_id_is_absent(self):
        destroyed = {"id": "vol_old", "state": "destroyed"}

        with patch.object(volumes, "get_result", return_value=destroyed):
            result = volumes.find_volume({}, "example", volume_id="vol_old")

        self.assertIsNone(result)
