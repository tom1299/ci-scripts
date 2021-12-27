import sys
import yaml
import semantic_version


def update_version():
    with open(chart_file, 'r') as chart_yaml:
        chart = yaml.load(chart_yaml, Loader=yaml.FullLoader)

        current_version = semantic_version.Version(chart.get("version"))
        print(f'Current chart version is {current_version}')
        new_version = semantic_version.Version(major=current_version.major,
                                               minor=current_version.minor, patch=current_version.patch + 1)
        print(f'New chart version is {new_version}')
        chart["version"] = str(new_version)

        print(f'Version updated to {new_version}')
        with open(chart_file, 'w') as stream:
            yaml.dump(chart, stream, sort_keys=False)


if __name__ == '__main__':
    if len(sys.argv) < 1:
        print('Need chart file')
        exit(1)

    chart_file = sys.argv[1]
    update_version()
