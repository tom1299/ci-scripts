import argparse
import time
import requests
import sys
import logging


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


def init_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    file_handler = logging.FileHandler('update_users.log')
    file_handler.setLevel(logging.INFO)
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
    return parser.parse_args()


def get_users(artifactory):
    logging.info("Getting all users")
    response = artifactory.session.get(f"{artifactory.api_url}/security/users")
    if not response.status_code == 200:
        logging.error(f"An error occurred while trying to get all users: {response.text}")
        return None
    return response.json()


def filter_users(all_users):
    return list(filter(filter_user, all_users))


def filter_user(user):
    name = user["name"]
    realm = user["realm"]
    if realm != "internal":
        logging.debug(f"User {name} with realm {realm} will not be updated")
        return False
    elif "@" not in name:
        logging.debug(f"User name {name} is not an email address and will not be updated")
        return False
    elif name.startswith("sa_"):
        logging.debug(f"User {name} is a system account and will not be updated")
        return False
    return True


def update_users(artifactory, dry_run=True, delay_in_seconds=2):
    all_users = get_users(artifactory)
    filtered_users = filter_users(all_users)

    print("Users in realm internal:")
    for user in filtered_users:
        print(user["name"])

    if not filtered_users:
        logging.error(f"Users could not be retrieved")
        return False

    logging.info(f"Starting update of users with realm internal")
    updates_done = 0

    for user in filtered_users:
        name = user["name"]

        response = artifactory.session.get(f"{artifactory.api_url}/security/users/{name}")
        if response.status_code != 200:
            logging.error(f"Could not get user details for user {name}: {response.text}")
            continue

        user_details = response.json()
        last_logged_ln_millis = user_details["lastLoggedInMillis"]
        is_admin = user_details["admin"]
        details_realm = user_details["realm"]
        internal_password_disabled = user_details["internalPasswordDisabled"]

        if not is_admin and not internal_password_disabled and last_logged_ln_millis == 0\
                and details_realm == "internal":
            logging.info(f"User {name} with realm {details_realm} has not yet logged in. "
                          f"Updating internalPasswordDisabled")
            user_details["internalPasswordDisabled"] = True
            updates_done += 1
            if not dry_run:
                logging.debug(f"User {name} will be updated")
                time.sleep(delay_in_seconds)
                response = artifactory.session.post(f"{artifactory.api_url}/security/users/{name}", json=user_details)
                if response.status_code != 200:
                    logging.error(f"Could not update user details for user {name}: {response.text}")
                else:
                    logging.debug(f"Successfully updated user details for user {name}")
            else:
                logging.info(f"User: {name}, {details_realm}, {last_logged_ln_millis}, {internal_password_disabled}"
                             f" would be updated")

    logging.info(f"{updates_done} users updated")


def main():
    init_logging()
    args = parse_args()
    artifactory = Artifactory(base_url=args.base_url, token=args.token)
    update_users(artifactory, args.dry_run)


if __name__ == '__main__':
    main()
