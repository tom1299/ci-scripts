import argparse
from dataclasses import dataclass
import glob
import os
import re
import shutil
import subprocess
from typing import Dict
import yaml


def to_string(obj):
    return obj.__class__.__name__ + "/" + obj.name


def find(element, dictionary):
    keys = element.split('/')
    current_dictionary = dictionary
    for key in keys:
        if re.search(r'[\d+]', key):
            key = int(re.search(r'\d+', key).group())
        elif key not in current_dictionary.keys():
            return None
        current_dictionary = current_dictionary[key]
    return current_dictionary


@dataclass
class FluxObject:
    name: str = None

    def __str__(self):
        return to_string(self)

    def __hash__(self):
        return hash(self.__str__())


@dataclass
class GitRepository(FluxObject):
    url: str = None
    tag: str = None


@dataclass
class HelmConfigValues(FluxObject):
    values: str = None


@dataclass
class HelmRelease(FluxObject):
    chart: str = None
    repo: GitRepository = None
    repo_name: str = None
    values: HelmConfigValues = None
    values_config_map_name: str = None


def build_git_repository(yaml_block) -> GitRepository:
    repo = GitRepository(name=find("metadata/name", yaml_block), url=find("spec/url", yaml_block))
    repo.tag = get_git_repository_tag(yaml_block)
    return repo


def get_git_repository_tag(yaml_block) -> str:
    ref = find("spec/ref", yaml_block)
    if "tag" in ref:
        return ref['tag']
    return ref['branch']


def build_helm_release(yaml_block) -> HelmRelease:
    return HelmRelease(name=find("metadata/name", yaml_block), chart=find("spec/chart/spec/chart", yaml_block),
                       repo_name=find("spec/chart/spec/sourceRef/name", yaml_block),
                       values_config_map_name=find("spec/valuesFrom/[0]/name", yaml_block))


def build_helm_values(yaml_block) -> HelmConfigValues | None:
    if "values.yaml" not in yaml_block["data"]:
        return None
    return HelmConfigValues(find("metadata/name", yaml_block), find("data/values.yaml", yaml_block))


Kind2Builder = {"GitRepository": build_git_repository, "HelmRelease": build_helm_release,
                "ConfigMap": build_helm_values}


def create_flux_objects_from_files(glob_pattern) -> Dict[str, object]:
    created_objects = {}
    files = glob.glob(glob_pattern)
    for file in files:
        with open(file, 'r') as file_stream:
            yaml_docs = yaml.load_all(file_stream, Loader=yaml.FullLoader)
            create_flux_objects_from_yaml_doc(created_objects, yaml_docs)
    return created_objects


def create_flux_objects_from_yaml_doc(created_objects, yaml_docs):
    for yaml_doc in yaml_docs:
        kind = find("kind", yaml_doc)
        if not kind:
            print(f"Could not determine kind from {yaml_doc!s:200.200}...")
        elif kind not in Kind2Builder.keys():
            print(f"Could not find builder for kind {kind} in {yaml_doc!s:200.200}...")
        else:
            create_flux_object_from_yaml_doc(created_objects, kind, yaml_doc)


def create_flux_object_from_yaml_doc(created_objects, kind, yaml_doc):
    builder = Kind2Builder[kind]
    flux_object = builder(yaml_doc)
    if not flux_object:
        print(f"Could not build flux object from {yaml_doc!s:200.200}...")
    else:
        created_objects[str(flux_object)] = flux_object


def compose_helm_releases(flux_objects):
    for release in {name: flux_object for name, flux_object in flux_objects.items() if
                    isinstance(flux_object, HelmRelease)}.values():  # type: HelmRelease
        release.repo = flux_objects[GitRepository.__name__ + "/" + release.repo_name]
        release.values = flux_objects[HelmConfigValues.__name__ + "/" + release.values_config_map_name]
        yield release


def parse_args():
    parser = argparse.ArgumentParser(description='Render k8s manifests from flux helm releases')
    parser.add_argument('--base-dir', '-b', nargs='?', dest="base_path", required=True,
                        help='Path to folder containing the flux manifests')
    parser.add_argument('--work-dir', '-w', nargs='?', dest="work_dir", required=True, help='Path to working directory')

    arguments = parser.parse_args()
    return arguments


def recreate_working_dir():
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

    all_flux_objects = create_flux_objects_from_files(f"{base_path}/**/*.yaml")

    recreate_working_dir()
    os.mkdir(output_dir)

    for helm_release in compose_helm_releases(all_flux_objects):
        git_clone_target_folder = f"{working_dir}/{helm_release.repo.name}"
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', helm_release.repo.tag, helm_release.repo.url,
                        git_clone_target_folder], check=True)

        release_value_file_name = f'{working_dir}/{helm_release.name}-values.yaml'
        with open(release_value_file_name, 'w') as value_file:
            value_file.write(helm_release.values.values)

        path_to_chart = git_clone_target_folder + "/" + helm_release.chart
        generated_manifests_file = output_dir + "/" + helm_release.name + ".yaml"
        with open(generated_manifests_file, "w") as helm_output:
            subprocess.run(['helm', '-f', release_value_file_name, 'template', '--debug', path_to_chart],
                           stdout=helm_output, check=True)

        assert os.path.exists(generated_manifests_file)
        assert os.path.getsize(generated_manifests_file) > 100
