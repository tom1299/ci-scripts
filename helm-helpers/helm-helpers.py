import argparse
from dataclasses import dataclass
import glob
import os
import shutil
import subprocess
from typing import Dict
import yaml


@dataclass
class GitRepository:
    name: str = None
    url: str = None
    tag: str = None


@dataclass
class HelmRelease:
    name: str = None
    chart: str = None
    repo: GitRepository = None
    values: dict = None


class GitRepositoryBuilder:

    @staticmethod
    def create(yaml_doc: dict) -> GitRepository:
        builder = GitRepositoryBuilder(yaml_doc)
        return builder.build()

    @staticmethod
    def create_git_repositories(sources_folder: str) -> Dict[str, GitRepository]:
        git_repos = {}
        source_files = glob.glob(f"{sources_folder}/*.yaml")
        for source_file in source_files:
            with open(source_file, 'r') as source_yaml:
                yaml_doc = yaml.load(source_yaml, Loader=yaml.FullLoader)
                git_repo = GitRepositoryBuilder.create(yaml_doc)
                git_repos[git_repo.name] = git_repo
        return git_repos

    def __init__(self, yaml_doc: dict):
        self.yaml_doc = yaml_doc

    def is_git_repository(self) -> bool:
        return self.yaml_doc["kind"] == "GitRepository"

    def build(self) -> GitRepository:
        if not self.is_git_repository():
            raise Exception(
                f"GitRepository can only be created from kind \"GitRepository\". "
                f"Kind {self.yaml_doc['kind']} is not supported")
        repo = GitRepository(name=self.yaml_doc['metadata']['name'], url=self.yaml_doc['spec']['url'])
        repo.tag = self.get_git_repository_tag()
        return repo

    def get_git_repository_tag(self) -> str:
        ref = self.yaml_doc['spec']['ref']
        if "tag" in ref:
            return ref['tag']
        elif "branch" in ref:
            return ref['branch']


def get_helm_values(config_map_path: str) -> dict:
    values = {}
    config_map_files = glob.glob(f"{config_map_path}/*.yaml")
    for config_map_file in config_map_files:
        add_helm_values(config_map_file, values)
    return values


def add_helm_values(config_map_file, values):
    with open(config_map_file, 'r') as config_map_yaml:
        config_map = yaml.load(config_map_yaml, Loader=yaml.FullLoader)

        if "values.yaml" not in config_map["data"]:
            print(f"config map {config_map['metadata']['name']} does not contain 'values.yaml' node")
            return

        values[config_map['metadata']['name']] = config_map["data"]["values.yaml"]


def get_helm_releases(helm_release_path: str, repos: dict, values: dict):
    helm_release_files = glob.glob(f"{helm_release_path}/*.yaml")
    helm_releases = []
    for helm_release_file in helm_release_files:
        add_helm_releases(helm_release_file, helm_releases, repos, values)
    return helm_releases


def add_helm_releases(helm_release_file, helm_releases, repos, values):
    with open(helm_release_file, 'r') as chart_yaml:
        yaml_documents = yaml.load_all(chart_yaml, Loader=yaml.FullLoader)
        for yaml_document in yaml_documents:
            if yaml_document["kind"] != "HelmRelease":
                continue
            print(f"Found helm release {yaml_document['metadata']['name']}")
            add_helm_release(helm_releases, repos, values, yaml_document)


def add_helm_release(helm_releases, repos, values, yaml_document):
    helm_release_name = yaml_document['metadata']['name']
    helm_chart = yaml_document['spec']['chart']['spec']['chart']
    source_ref = yaml_document["spec"]["chart"]["spec"]["sourceRef"]
    if not source_ref["kind"] == "GitRepository":
        print(f"source reference of helm release {helm_release_name}, {source_ref} is not of kind GitRepository")
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
    helm_release = HelmRelease(name=helm_release_name, chart=helm_chart, repo=repo, values=chart_values)
    helm_releases.append(helm_release)


def parse_args():
    parser = argparse.ArgumentParser(description='Render k8s manifests from flux helm releases')
    parser.add_argument('--base-dir', '-b', nargs='?', dest="base_path", required=True,
                        help='Path to folder containing the flux manifests')
    parser.add_argument('--work-dir', '-w', nargs='?', dest="work_dir", required=True, help='Path to working directory')

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()

    base_path = args.base_path
    work_dir = args.work_dir
    source_path = f"{base_path}/sources"
    helm_release_path = f"{base_path}/helmreleases"
    config_maps_path = f"{base_path}/configmaps"

    repos = GitRepositoryBuilder.create_git_repositories(sources_folder=source_path)
    values = get_helm_values(config_maps_path)

    try:
        shutil.rmtree(work_dir)
    except FileNotFoundError:
        pass
    os.mkdir(work_dir)

    helm_releases = get_helm_releases(helm_release_path, repos, values)

    if not helm_releases:
        print(f"No helm releases found in {helm_release_path}")
        exit(1)

    helm_output_dir = work_dir + "/generated"
    os.mkdir(helm_output_dir)
    for helm_release in helm_releases:
        repo_dir = f"{work_dir}/{helm_release.repo.name}"
        subprocess.run(
            ['git', 'clone', '--depth', '1', '--branch', helm_release.repo.tag, helm_release.repo.url, repo_dir])

        value_file_name = f'{work_dir}/{helm_release.name}-values.yaml'
        with open(value_file_name, 'w') as value_file:
            value_file.write(helm_release.values)

        chart_dir = repo_dir + "/" + helm_release.chart
        chart_target = helm_output_dir + "/" + helm_release.name + ".yaml"
        with open(chart_target, "w") as helm_output:
            subprocess.run(['helm', '-f', value_file_name, 'template', '--debug', chart_dir], stdout=helm_output)

        assert os.path.exists(chart_target)
        assert os.path.getsize(chart_target) > 100
