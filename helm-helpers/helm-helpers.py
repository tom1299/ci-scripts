import argparse
from dataclasses import dataclass
import glob
import os
import re
import shutil
import subprocess

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


@dataclass
class HelmConfigValues:
    name: str = None
    values: dict = None


def find(element, dictionary):
    keys = element.split('/')
    rv = dictionary
    for key in keys:
        if re.search('[\d+]', key):
            key = int(re.search('\d+', key).group())
        rv = rv[key]
    return rv


def create_from_files(folder: str, clazz, *args) -> dict:
    created_objects = {}
    yaml_files = glob.glob(f"{folder}/*.yaml")
    for yaml_file in yaml_files:
        with open(yaml_file, 'r') as file_content:
            yaml_docs = yaml.load_all(file_content, Loader=yaml.FullLoader)
            for yaml_doc in yaml_docs:
                builder = clazz(yaml_doc, *args)
                created_object = builder.build()
                if created_object:
                    created_objects[created_object.name] = created_object
    return created_objects


class GitRepositoryBuilder:

    def __init__(self, yaml_doc: dict):
        self.yaml_doc = yaml_doc

    def is_git_repository(self) -> bool:
        return self.yaml_doc["kind"] == "GitRepository"

    def build(self) -> GitRepository:
        if not self.is_git_repository():
            raise Exception(f"GitRepository can only be created from kind \"GitRepository\". "
                            f"Kind {self.yaml_doc['kind']} is not supported")
        repo = GitRepository(name=find("metadata/name", self.yaml_doc), url=find("spec/url", self.yaml_doc))
        repo.tag = self.get_git_repository_tag()
        return repo

    def get_git_repository_tag(self) -> str:
        ref = find("spec/ref", self.yaml_doc)
        if "tag" in ref:
            return ref['tag']
        elif "branch" in ref:
            return ref['branch']


class HelmReleaseBuilder:

    def __init__(self, yaml_doc: dict, git_repositories, config_values):
        self.yaml_doc = yaml_doc
        self.git_repositories = git_repositories
        self.config_values = config_values

    def build(self) -> HelmRelease | None:
        if not self.is_helm_release():
            return
        return HelmRelease(name=self.get_helm_release_name(), chart=self.get_helm_chart_name(), repo=self.get_repo(),
                           values=self.get_config_values())

    def get_helm_release_name(self):
        return find("metadata/name", self.yaml_doc)

    def get_helm_chart_name(self):
        return find("spec/chart/spec/chart", self.yaml_doc)

    def get_repo(self) -> GitRepository | None:
        source_ref_name = find("spec/chart/spec/sourceRef/name", self.yaml_doc)
        if not self.is_source_ref_git_repository():
            return
        repo = repos[source_ref_name]
        return repo

    def is_helm_release(self) -> bool:
        return self.yaml_doc["kind"] == "HelmRelease"

    def is_source_ref_git_repository(self) -> bool:
        return find("spec/chart/spec/sourceRef/kind", self.yaml_doc) == "GitRepository"

    def get_config_values(self):
        config_map_name = find("spec/valuesFrom/[0]/name", self.yaml_doc)
        return values[config_map_name]


class HelmConfigValuesBuilder:

    def __init__(self, yaml_doc: dict):
        self.yaml_doc = yaml_doc

    def build(self) -> HelmConfigValues | None:
        if "values.yaml" not in self.yaml_doc["data"]:
            return
        return HelmConfigValues(find("metadata/name", self.yaml_doc), find("data/values.yaml", self.yaml_doc))


def parse_args():
    parser = argparse.ArgumentParser(description='Render k8s manifests from flux helm releases')
    parser.add_argument('--base-dir', '-b', nargs='?', dest="base_path", required=True,
                        help='Path to folder containing the flux manifests')
    parser.add_argument('--work-dir', '-w', nargs='?', dest="work_dir", required=True, help='Path to working directory')

    arguments = parser.parse_args()
    return arguments


def clean_working_dir():
    try:
        shutil.rmtree(working_dir)
    except FileNotFoundError:
        pass
    os.mkdir(working_dir)


if __name__ == '__main__':
    args = parse_args()

    base_path = args.base_path
    working_dir = args.work_dir
    path_to_git_repos = f"{base_path}/sources"
    path_to_helm_releases = f"{base_path}/helmreleases"
    path_to_config_maps = f"{base_path}/configmaps"
    output_dir = working_dir + "/generated"

    repos = create_from_files(path_to_git_repos, GitRepositoryBuilder)
    values = create_from_files(path_to_config_maps, HelmConfigValuesBuilder)

    helm_releases = create_from_files(path_to_helm_releases, HelmReleaseBuilder, repos, values)

    if not helm_releases:
        print(f"No helm releases found in {path_to_helm_releases}")
        exit(1)

    clean_working_dir()

    os.mkdir(output_dir)
    for helm_release in helm_releases.values():
        git_clone_target_folder = f"{working_dir}/{helm_release.repo.name}"
        subprocess.run(
            ['git', 'clone', '--depth', '1', '--branch', helm_release.repo.tag, helm_release.repo.url, git_clone_target_folder])

        release_value_file_name = f'{working_dir}/{helm_release.name}-values.yaml'
        with open(release_value_file_name, 'w') as value_file:
            value_file.write(helm_release.values.values)

        path_to_chart = git_clone_target_folder + "/" + helm_release.chart
        generated_manifests_file = output_dir + "/" + helm_release.name + ".yaml"
        with open(generated_manifests_file, "w") as helm_output:
            subprocess.run(['helm', '-f', release_value_file_name, 'template', '--debug', path_to_chart], stdout=helm_output)

        assert os.path.exists(generated_manifests_file)
        assert os.path.getsize(generated_manifests_file) > 100
