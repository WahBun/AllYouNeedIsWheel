#!/usr/bin/env python3
"""Check native catalog coverage and interpolation safety; optionally check a build's extracted keys."""
import argparse
import collections
import json
from pathlib import Path
import re

FORMAT = re.compile(r'%(?:\d+\$)?[-+#0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hlLzjt])?[@diuoxXfFeEgGcCsSpaA]')


def placeholders(text):
    return collections.Counter(re.sub(r'^%(?:\d+\$)', '%', value) for value in FORMAT.findall(text.replace('%%', '')))


def audit(catalog, extracted=None):
    strings = catalog['strings']
    errors = []
    for key, entry in strings.items():
        if entry.get('shouldTranslate') is False:
            continue
        source = entry.get('localizations', {}).get('en', {}).get('stringUnit', {}).get('value', key)
        for language in ('zh-Hans', 'zh-Hant'):
            value = entry.get('localizations', {}).get(language, {}).get('stringUnit', {}).get('value')
            if not value:
                errors.append(f'{language}: missing {key!r}')
            elif placeholders(source) != placeholders(value):
                errors.append(f'{language}: interpolation mismatch {key!r}')
    if extracted:
        for path in sorted(Path(extracted).glob('*.stringsdata')):
            for row in json.loads(path.read_text()).get('tables', {}).get('Localizable', []):
                if row['key'] not in strings:
                    errors.append(f'{path.stem}: uncatalogued {row["key"]!r}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=Path(__file__).resolve().parents[1] / 'ios/Wheel/Localizable.xcstrings')
    parser.add_argument('--extracted-dir', type=Path)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    errors = audit(catalog, args.extracted_dir)
    if errors:
        print('\n'.join(errors))
        return 1
    print(f'Localization audit passed: {len(catalog["strings"])} keys, Simplified/Traditional Chinese and interpolation checked.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
