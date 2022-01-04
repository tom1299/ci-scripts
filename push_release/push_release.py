from git import Repo
import yaml
import semantic_version
import sys
import os

new_version = None


def commit_changes(repository, commit_message):
    print(f'Committing all changes with commit message {commit_message}')
    print(f'Repository contains the following untracked files {repository.untracked_files}')

    head_commit = repository.head.commit
    changed_files = list(map(lambda change: change.a_path, head_commit.diff(None)))
    print(f'Repository contains the following changed files {changed_files}')

    repository.git.add(all=True)
    repository.index.commit(commit_message)


def create_tag(repository):
    print(f'Creating new tag {new_version}')
    repository.git.tag('-a', str(new_version), repository.head.commit, '-m', str(new_version))


def update_chart_version(chart_file):
    global new_version
    with open(chart_file, 'r') as chart_yaml:
        chart = yaml.load(chart_yaml, Loader=yaml.FullLoader)
        current_version = semantic_version.Version(chart.get("version"))
        print(f'Current chart version is {current_version}')
        new_version = semantic_version.Version(major=current_version.major,
                                               minor=current_version.minor, patch=current_version.patch + 1)
        print(f'New chart version is {new_version}')
        chart["version"] = str(new_version)

    with open(chart_file, 'w') as stream:
        yaml.dump(chart, stream)

    return new_version


def update_helm_release(release_file, src_repo_name):
    with open(release_file, 'r') as release_yaml:
        documents = yaml.load_all(release_yaml, Loader=yaml.FullLoader)
        for doc in documents:
            if doc.get("spec").get("url") and src_repo_name in doc.get("spec").get("url"):
                current_tag = doc.get("spec").get("ref").get("tag")
                print(f'Current tag is {current_tag}')
                print(f'New chart version is {new_version}')
                doc.get("spec").get("ref")["tag"] = str(new_version)
                break

        with open(release_file, 'w') as stream:
            yaml.dump(doc, stream)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Need repo paths and commit message as arguments')
        exit(1)

    helm_repo_path = sys.argv[1]
    chart_path = sys.argv[2]
    flux_repo_path = sys.argv[3]
    message = sys.argv[4]

    helm_repo = Repo(helm_repo_path)

    if not helm_repo.is_dirty():
        print('Repository does not contain any changes')

    new_version = update_chart_version(helm_repo_path + chart_path)
    commit_changes(helm_repo, message)
    create_tag(helm_repo)
    helm_repo.git.push('origin', str(new_version))
    helm_repo.git.push('origin')

    flux_repo = Repo(flux_repo_path)

    update_helm_release(flux_repo_path + "/sources/helm-repo.yaml", os.path.basename(os.path.normpath(helm_repo_path)))
    commit_changes(flux_repo, message)
    flux_repo.git.push('origin')
