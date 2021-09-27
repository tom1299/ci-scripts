import argparse
import sre_parse

import requests
import sys
import logging
from requests.auth import HTTPBasicAuth


class Artifactory:

    def __init__(self, base_url: str, user: str, token: str):
        self._base_url = base_url
        self._session = requests.Session()
        self._session.verify = True
        self._session.auth = HTTPBasicAuth(user, token)
        self._session.headers.update({"content-type": "application/json"})
        resp = self.session.get(self.base_url + "/artifactory/api/system/ping")
        assert resp.text == "OK", "Could not connect to artifactory"
        logging.info(f"Successfully connected to {self.base_url}")

    @property
    def session(self):
        return self._session

    @property
    def base_url(self):
        return self._base_url

    @property
    def ui_api_url(self):
        return f"{self.base_url}/ui/api/v1/ui"


class ScanOperation:

    def __init__(self, artifactory: Artifactory, component_id: str, repo_key: str):
        self._artifactory = artifactory
        self._component_id = component_id
        self._component_path = self.convert_component_id_to_path()
        self._repo_key = repo_key

    def is_scanned(self) -> bool:
        response = self._artifactory.session.get(f"{self._artifactory.ui_api_url}/artifactxray?path="
                                                 f"{self._component_path}/manifest.json&repoKey={self._repo_key}")
        xray_status = response.json()

        if response.status_code == 404:
            logging.info(f"Artifact {self._component_id} has not yet been scanned")
            return False
        elif response.status_code == 200 and xray_status["xrayIndexStatus"] == "Not indexed":
            logging.info(f"Artifact {self._component_id} has not yet been scanned")
            return False
        elif response.status_code == 200:
            logging.info(f"Artifact {self._component_id} has already been scanned")
            return True
        else:
            logging.error(f"Could not determine status of artifact  {self._component_id} from response {response}")
            raise RuntimeError(f"Could not determine status of artifact  {self._component_id} from response {response}")

    def scan(self) -> bool:
        pass

    def convert_component_id_to_path(self):
        last_colon_idx = self._component_id.rfind(":")
        type_index = self._component_id.find("//") + 2
        return self._component_id[type_index:last_colon_idx] + "/" + self._component_id[last_colon_idx+1:]


if __name__ == '__main__':
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)

    parser = argparse.ArgumentParser()
    parser.add_argument("--user", help="The artifactory user name")
    parser.add_argument("--token", help="The api token of the user")
    parser.add_argument("--component-id",
                        help="The component id. E.g.: 'docker://myrepo/path/component:5.0.50'")
    parser.add_argument("--repo-key", help="The repo-key")
    parser.add_argument("--base-url", help="The url to artifactory")
    args = parser.parse_args()

    artifactory = Artifactory(base_url=args.base_url, user=args.user, token=args.token)
    scan_operation = ScanOperation(artifactory, args.component_id, args.repo_key)
    is_scanned: bool = scan_operation.is_scanned()

