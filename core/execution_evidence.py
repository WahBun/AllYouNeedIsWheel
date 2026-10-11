"""Conservative identity grouping for read-only execution/fee evidence."""
from collections import defaultdict


def identity(execution):
    account = str(getattr(execution, 'acctNumber', '') or '')
    perm = str(getattr(execution, 'permId', '') or '')
    order = ('perm', perm) if perm not in ('', '0') else (
        'api', str(getattr(execution, 'clientId', '')), str(getattr(execution, 'orderId', '')),
        str(getattr(execution, 'orderRef', '') or ''))
    return account, order


def groups(records, execution_of=lambda item: item):
    """Return nonconflicting duplicate groups and whether evidence is unambiguous.

    Four-segment correction families are uncertain; don't guess revision ordering.
    Five-segment combo-leg IDs remain distinct. ID-less legacy rows stay separate.
    """
    identified = True
    grouped = defaultdict(list)
    corrections = defaultdict(set)
    for index, record in enumerate(records):
        execution = execution_of(record)
        key = str(getattr(execution, 'execId', '') or '')
        identified = identified and bool(key)
        scoped = identity(execution)
        group_key = scoped, key if key else ('missing', index)
        grouped[group_key].append(record)
        parts = key.split('.')
        if len(parts) == 4 and parts[-1].isdigit():
            corrections[(scoped, '.'.join(parts[:-1]))].add(group_key)
    ambiguous = set().union(*(keys for keys in corrections.values() if len(keys) > 1))
    result = []
    for key, values in grouped.items():
        signatures = {(getattr(execution_of(v), 'shares', None),
                       getattr(execution_of(v), 'price', None),
                       getattr(execution_of(v), 'side', None)) for v in values}
        if len(signatures) > 1:
            ambiguous.add(key)
        if key not in ambiguous:
            result.append(values)
    return result, not ambiguous and identified
