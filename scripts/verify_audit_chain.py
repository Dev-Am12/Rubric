#!/usr/bin/env python3
"""Verify an exported Rubric audit chain using only the Python standard library."""

import argparse
import hashlib
import json
import sys


GENESIS_HASH = '0' * 64


def canonical_json_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
    ).encode('utf-8')


def verify(document):
    if not isinstance(document, dict):
        return False, 1, 'export root must be a JSON object'
    if document.get('genesis_hash') != GENESIS_HASH:
        return False, 1, 'invalid genesis hash'
    entries = document.get('entries')
    head = document.get('head')
    if not isinstance(entries, list):
        return False, 1, 'entries must be a JSON array'
    if not isinstance(head, dict) or not isinstance(head.get('seq'), int) or not isinstance(head.get('hash'), str):
        return False, 1, 'head must include an integer seq and string hash'
    expected_prev = GENESIS_HASH
    expected_seq = 1
    for entry in entries:
        if not isinstance(entry, dict):
            return False, expected_seq, 'entry must be a JSON object'
        seq = entry.get('seq')
        if seq != expected_seq:
            return False, expected_seq, f'expected seq {expected_seq}, found {seq}'
        if entry.get('prev_hash') != expected_prev:
            return False, seq, 'previous hash does not match'
        try:
            body = {key: entry[key] for key in (
                'seq', 'prev_hash', 'created_at', 'actor', 'action', 'target', 'payload',
            )}
            actual_hash = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        except (KeyError, TypeError, ValueError) as exc:
            return False, seq, f'invalid canonical entry: {exc}'
        if actual_hash != entry.get('entry_hash'):
            return False, seq, 'entry hash does not match'
        expected_prev = actual_hash
        expected_seq += 1
    final_seq = expected_seq - 1
    if head.get('seq') != final_seq:
        return False, min(head['seq'], final_seq) + 1, 'head sequence does not match entries'
    if head.get('hash') != expected_prev:
        return False, max(1, final_seq), 'head hash does not match entries'
    return True, None, head['hash']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export_file', help='JSON audit-chain export file')
    args = parser.parse_args(argv)
    try:
        with open(args.export_file, 'r', encoding='utf-8') as source:
            document = json.load(source, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f'audit chain invalid: {exc}', file=sys.stderr)
        return 1
    ok, first_bad_seq, detail = verify(document)
    if not ok:
        print(f'audit chain invalid at seq {first_bad_seq}: {detail}', file=sys.stderr)
        return 1
    print(f'audit chain valid; head_hash={detail}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
