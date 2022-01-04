import fnmatch
import logging
import os
import sys
import yaml


def all_files_in_folder(folder):
    for folder, sub_folder, files in os.walk(folder):
        for file in files:
            absolute_path = os.path.join(folder, file)
            yield absolute_path, file


def get_policy_files_from_folder(folder):
    all_files = all_files_in_folder(folder)
    exclude = ['check_deprecated_apis.yaml', "disallow_default_namespace.yaml"]
    def only_yaml_files(file_info): return fnmatch.fnmatch(file_info[0], '*.yaml')
    def no_test_files(file_info): return not fnmatch.fnmatch(file_info[0], '*test.yaml')
    def exclude_files(file_info): return file_info[1] not in exclude

    filtered_files = filter(exclude_files,filter(no_test_files, filter(only_yaml_files, all_files)))

    return filtered_files


if __name__ == '__main__':
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if len(sys.argv) < 1:
        print('Need policy files folder')
        exit(1)
    get_policy_files_from_folder(sys.argv[1])
