import sys
import yaml


def update_chart_version():
    with open(chart_file, 'r') as chart_yaml:
        chart = yaml.load(chart_yaml, Loader=yaml.FullLoader)

        dependency_fount = False
        for dependency in chart["dependencies"]:
            if dependency["name"] == dependency_name:
                print(f'Found dependency {dependency_name}')
                print(f'Current version is {dependency["version"]}')
                print(f'Setting new version is {new_version}')
                dependency["version"] = new_version
                dependency_fount = True
                break

        if not dependency_fount:
            print(f'Dependency {dependency_name} not found')
            exit(1)
        else:
            print(f'Dependency {dependency_name} updated to {new_version}')
            with open(chart_file, 'w') as stream:
                yaml.dump(chart, stream, sort_keys=False)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Need chart file, dependency name and version')
        exit(1)

    chart_file = sys.argv[1]
    dependency_name = sys.argv[2]
    new_version = sys.argv[3]

    update_chart_version()
