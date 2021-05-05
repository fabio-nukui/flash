import json
import pathlib

STRATEGY_FILES_DIR = pathlib.Path('strategy_files')


def migrate_file(filepath: pathlib.Path):
    data = json.load(open(filepath))
    data['addresses']['route_0'] = data['addresses'].pop('second_route')
    data['addresses']['route_1'] = data['addresses'].pop('first_route')
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)


for strategy_dir in STRATEGY_FILES_DIR.iterdir():
    if not strategy_dir.is_dir():
        continue
    for arb_pair_dir in (strategy_dir / 'arb_pairs').iterdir():
        summary_file = arb_pair_dir / 'summary.json'
        if summary_file.exists():
            migrate_file(summary_file)
        backup_file = arb_pair_dir / 'summary_BAK.json'
        if backup_file.exists():
            migrate_file(backup_file)
