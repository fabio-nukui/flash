import json
import pathlib

contracts_dir = pathlib.Path('build/contracts')
deployed_contracts_dir = pathlib.Path('deployed_contracts')

KEEP_FIELDS = [
    'contractName',
    'abi',
    'compiler',
    'networks',
    'schemaVersion',
]

TEST_NETWORKS = [5777]


def main():
    for path in contracts_dir.iterdir():
        with open(path) as f:
            data = json.load(f)
        data['networks'] = {
            key: value
            for key, value in data['networks'].items()
            if int(key) not in TEST_NETWORKS
        }
        if not data['networks']:
            continue
        write_data = {
            field: data[field]
            for field in KEEP_FIELDS
        }
        write_filepath = deployed_contracts_dir / path.name
        with open(write_filepath, 'w') as f:
            json.dump(write_data, f, indent=2)


if __name__ == '__main__':
    main()
