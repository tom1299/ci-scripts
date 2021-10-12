import argparse
import json
import requests
import sys
import logging
from itertools import islice


class Artifactory:

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url
        self._session = requests.Session()
        self._session.verify = True
        self._session.headers.update(
            {"X-JFrog-Art-Api": token, "content-type": "application/json"})
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
    def api_url(self):
        return f"{self.base_url}/artifactory/api"

    @property
    def item_url(self):
        return f"{self.base_url}/artifactory"


def init_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler('copy-properties.log')
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    root.addHandler(handler)
    root.addHandler(file_handler)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="The api token of the user")
    parser.add_argument("--base-url", help="The url to artifactory")
    parser.add_argument("--dry-run", help="The url to artifactory", default=True)
    parser.add_argument("--source-file-path", help="The path the the source file")
    parser.add_argument("--target-file-path", help="The path the the target file")
    parser.add_argument("--properties-count", help="The number of properties to move", default=100)
    return parser.parse_args()


def get_properties(artifactory, file_path):
    logging.info(f"Getting properties of file {file_path}")
    response = artifactory.session.get(f"{artifactory.item_url}/{file_path}?properties")
    if not response.status_code == 200:
        logging.error(f"An error occurred while trying to get properties for file {file_path}: {response.text}")
        return None
    return response.json()


def add_properties(artifactory, properties, file_path):
    logging.info(f"Updating properties of file {file_path} with {len(properties)} properties")
    for prop_key, prop_value in properties.items():
        properties[prop_key] = prop_value[0]
    new_props = json.dumps({"props": properties})
    response = artifactory.session.patch(f"{artifactory.api_url}/metadata/{file_path}?&recursive=0", data=new_props)
    if not response.ok:
        logging.error(f"An error occurred while trying to update the properties of file {file_path}: {response.text}")
        return False
    return True


def delete_properties(artifactory, properties, file_path):
    logging.info(f"Deleting {len(properties)} properties of file {file_path} ")
    props = ",".join(properties.keys())
    response = artifactory.session.delete(f"{artifactory.api_url}/storage/{file_path}?properties={props}&recursive=0")
    if not response.ok:
        logging.error(f"An error occurred while trying to delete some properties of file {file_path}: {response.text}")
        return False
    return True


def main():
    init_logging()
    args = parse_args()
    artifactory = Artifactory(base_url=args.base_url, token=args.token)
    source_props = get_properties(artifactory, args.source_file_path)["properties"]
    logging.info(f"Got {len(source_props)} source properties")
    target_props = get_properties(artifactory, args.target_file_path)["properties"]
    logging.info(f"Got {len(target_props)} target properties")

    properties_difference = {}
    for source_property_key, source_property_value in source_props.items():
        if source_property_key not in target_props:
            properties_difference[source_property_key] = source_property_value

    sorted_properties_difference = dict(sorted(properties_difference.items()))
    logging.info(f"Different properties count is {len(sorted_properties_difference)}")

    properties_count = int(args.properties_count)
    logging.debug(f"Getting first: {properties_count} from properties difference")

    first_n_properties_keys = list(islice(sorted_properties_difference, properties_count))
    first_n_properties = {}
    for prop_key in first_n_properties_keys:
        first_n_properties[prop_key] = sorted_properties_difference[prop_key]

    logging.info(f"First: {properties_count} different properties: {first_n_properties}")
    properties_added = add_properties(artifactory, first_n_properties, args.target_file_path)
    if properties_added:
        logging.info(f"Successfully added properties to {args.target_file_path}."
                     f" Deleting them from {args.source_file_path}")
        properties_deleted = delete_properties(artifactory, first_n_properties, args.source_file_path)
        if not properties_deleted:
            logging.error(f"Could not delete properties from {args.source_file_path}.")
            exit(1)
        logging.info(f"Properties successfully copied")
        exit(0)

    logging.error(f"Could not add properties to {args.target_file_path}.")
    exit(1)


if __name__ == '__main__':
    main()
