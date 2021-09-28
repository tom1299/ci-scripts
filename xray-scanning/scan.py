import argparse
import requests
import sys
import logging
from requests.auth import HTTPBasicAuth
from retrying import retry, RetryError


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

    @property
    def xray_api_url(self):
        return f"{self.base_url}/xray/api/v1"


class ScanOperation:

    def __init__(self, artifactory: Artifactory, component_id: str, repo_key: str):
        self._artifactory = artifactory
        self._component_id = component_id
        self._component_path = self.convert_component_id_to_path()
        self._repo_key = repo_key
        self._report_id = None

    def is_scanned(self) -> bool:
        response = self._artifactory.session.get(f"{self._artifactory.ui_api_url}/artifactxray?path="
                                                 f"{self._component_path}/manifest.json&repoKey={self._repo_key}")
        if response.status_code == 404:
            logging.info(f"Artifact {self._component_id} has not yet been scanned")
            return False
        elif response.status_code == 200:
            xray_status = response.json()
            if xray_status["xrayIndexStatus"] == "Not indexed":
                logging.info(f"Artifact {self._component_id} has not yet been scanned")
                return False
            else:
                logging.info(f"Artifact {self._component_id} has already been scanned")
                return True
        else:
            logging.error(f"Could not determine status of artifact  {self._component_id} from response {response}")
            raise RuntimeError(f"Could not determine status of artifact  {self._component_id} from response {response}")

    def scan(self) -> bool:
        logging.info(f"Start scanning of artifact {self._component_id}")
        try:
            response = self._artifactory.session.post(f"{self._artifactory.xray_api_url}/scanArtifact",
                                                      json={"componentID": f"{self._component_id}"})
            if response.status_code != 200:
                logging.info(f"Scanning of artifact {self._component_id} could not be started. Reason: {response.text}")
                return False

            self.wait_for_scan_to_complete()
            return True
        except RetryError:
            logging.info(f"Scanning of artifact {self._component_id} did not complete in time")
            return False

    def retry_if_not_yet_scanned(result):
        if not result:
            logging.debug(f"Scan of artifact not yet complete")
        return not result

    @retry(wait_fixed=3000, stop_max_attempt_number=2, retry_on_result=retry_if_not_yet_scanned)
    def wait_for_scan_to_complete(self):
        return self.is_scanned()

    def convert_component_id_to_path(self):
        last_colon_idx = self._component_id.rfind(":")
        type_index = self._component_id.find("//") + 2
        return self._component_id[type_index:last_colon_idx] + "/" + self._component_id[last_colon_idx+1:]

    def get_report(self):
        return self.create_report()

    def create_report(self):
        logging.info(f"Start report creation for artifact {self._component_id}")
        json = {
            "name": f"{self._repo_key}",
            "resources": {
                "repositories": [
                    {
                        "name": f"{self._repo_key}"
                    }
                ]
            },
            "filters": {
                "impacted_artifact": f"{self._component_id}",
                "severities": [
                    "High",
                    "Critical"
                ]
            }
        }
        response = self._artifactory.session.post(f"{self._artifactory.xray_api_url}/reports/vulnerabilities",
                                                  json=json)
        if response.status_code != 200:
            logging.info(f"Report creation for artifact {self._component_id} could not be started")
            return None

        self._report_id = response.json()["report_id"]
        self.wait_for_report_creation()

    def retry_if_not_yet_completed(result):
        if not result:
            logging.debug(f"Creation of report not yet complete")
        return not result

    @retry(wait_fixed=2000, stop_max_attempt_number=20, retry_on_result=retry_if_not_yet_completed)
    def wait_for_report_creation(self):
        logging.info(f"Waiting for report {self._report_id} to be completed")
        response = self._artifactory.session.get(f"{self._artifactory.xray_api_url}/reports/{self._report_id}")

        if response.status_code == 404:
            logging.debug(f"Report {self._report_id} not yet completed")
            return False
        elif response.status_code == 200:
            report_metadata = response.json()

            if report_metadata["status"] != "completed":
                logging.debug(f"Report {self._report_id} not yet completed: {report_metadata}")
                return False
            elif report_metadata["num_of_processed_artifacts"] == 0:
                logging.error(f"Report {self._report_id} completed without any processed artifacts")
                raise RuntimeError(f"Report {self._report_id} completed without any processed artifacts")
        else:
            logging.error(f"Report #{self._report_id} could not be completed: {response.text}")
            raise RuntimeError(f"Report #{self._report_id} could not be completed: {response.text}")

        return True

    def delete_report(self):
        pass


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

    if True:
        logging.info(f"Artifact {args.component_id} has not yet been scanned. Starting scan")
        if not scan_operation.scan():
            logging.error(f"Artifact {args.component_id} could not be scanned. Aborting")
            exit(1)
    else:
        logging.info(f"Artifact {args.component_id} has already been scanned. "
                     f"Aborting to avoid redundant report creation")
        exit(1)

    report = scan_operation.get_report()
    if not report:
        logging.error(f"Vulnerability report for artifact {args.component_id} could not created. Aborting")
        exit(1)

    # TODO: Store report here
    scan_operation.delete_report()

