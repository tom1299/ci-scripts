import glob
import yaml


class GitRepositoryMetaData:
    def __init__(self):
        self.name: str
        self.url: str
        self.tag: str
        self.branch: str

    def __str__(self):
        return str(self.__dict__)


class HelmReleaseMetaData:
    def __init__(self):
        self.name: str
        self.repo: GitRepositoryMetaData
        self.values: dict

    def __str__(self):
        data = self.__dict__
        data["repo"] = self.repo.__dict__
        return str(data)


def get_git_repositories(source_path: str) -> dict:
    repos = {}
    source_files = glob.glob(f"{source_path}/*.yaml")
    for source_file in source_files:
        with open(source_file, 'r') as source_yaml:
            source_document = yaml.load(source_yaml, Loader=yaml.FullLoader)
            if source_document["kind"] == "GitRepository":
                print(f"Found git repository {source_document['metadata']['name']}")
                repo = GitRepositoryMetaData()
                repo.name = source_document['metadata']['name']
                repo.url = source_document['spec']['url']

                if "tag" in source_document['spec']['ref']:
                    repo.tag = source_document['spec']['ref']['tag']
                elif "branch" in source_document['spec']['ref']:
                    repo.branch = source_document['spec']['ref']['branch']
                repos[repo.name] = repo
    return repos


def get_values(config_map_path: str) -> dict:
    values = {}
    config_map_files = glob.glob(f"{config_map_path}/*.yaml")
    for config_map_file in config_map_files:
        with open(config_map_file, 'r') as config_map_yaml:
            config_map = yaml.load(config_map_yaml, Loader=yaml.FullLoader)
            if config_map["kind"] == "ConfigMap":
                print(f"Found config map {config_map['metadata']['name']}")

            if "values.yaml" not in config_map["data"]:
                print(
                    f"config map {config_map['metadata']['name']} does not contain 'values.yaml' node")
                continue
            values[config_map['metadata']['name']] = config_map["data"]["values.yaml"]
    return values


def get_helm_releases(helm_release_path: str, repos: dict, values: dict):
    helm_release_files = glob.glob(f"{helm_release_path}/*.yaml")
    helm_releases = []
    for helm_release_file in helm_release_files:
        with open(helm_release_file, 'r') as chart_yaml:
            yaml_documents = yaml.load_all(chart_yaml, Loader=yaml.FullLoader)
            for yaml_document in yaml_documents:
                if yaml_document["kind"] == "HelmRelease":
                    print(f"Found helm release {yaml_document['metadata']['name']}")
                else:
                    continue
                helm_release_name = yaml_document['metadata']['name']

                source_ref = yaml_document["spec"]["chart"]["spec"]["sourceRef"]
                if not source_ref["kind"] == "GitRepository":
                    print(
                        f"source reference of helm release {helm_release_name}, {source_ref} is not of kind GitRepository")
                    exit(1)
                repo = repos[source_ref["name"]]
                if not repo:
                    print(f"No repository found with name {source_ref['name']}")
                    exit(1)

                # TODO: Check type and size
                config_map_name = yaml_document["spec"]["valuesFrom"][0]["name"]
                chart_values = values[config_map_name]
                if not chart_values:
                    print(f"No values found with name {config_map_name}")
                    exit(1)

                helm_release = HelmReleaseMetaData()
                helm_release.name = helm_release_name
                helm_release.repo = repo
                helm_release.values = chart_values
                helm_releases.append(helm_release)
    return helm_releases


if __name__ == '__main__':
    base_path = "~/git/wlan-flux"
    source_path = f"{base_path}/sources"
    helm_release_path = f"{base_path}/helmreleases"
    config_maps_path = f"{base_path}/configmaps"

    repos = get_git_repositories(source_path)
    values = get_values(config_maps_path)

    helm_releases = get_helm_releases(helm_release_path, repos, values)
    for helm_release in helm_releases:
        pass
