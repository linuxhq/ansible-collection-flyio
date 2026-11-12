# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


class ModuleDocFragment:
    DOCUMENTATION = r"""
options:
  api_token:
    type: str
    description:
      - Fly.io API token.
      - If not set, the value of the E(FLY_API_TOKEN) environment variable is used.
      - Required when E(FLY_API_TOKEN) is not set.
"""
