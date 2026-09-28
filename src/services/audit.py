"""Transactional append, verification, export, and organizer reads for audit history."""

import builtins
import hashlib
import json

from django.core.paginator import Paginator
from django.db import connections, transaction
from django.utils import timezone

from accounts.actors import PermissionDenied
from audit.models import AuditChainHead, AuditLogEntry


GENESIS_HASH = '0' * 64
POSTGRES_ADVISORY_LOCK_KEY = 0x4155444954


def canonical_json_bytes(value):
    """Canonical byte representation used by both the chain and verifier script."""
    return json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
    ).encode('utf-8')


def _entry_hash(*, seq, prev_hash, created_at, actor, action, target, payload):
    body = {
        'seq': seq,
        'prev_hash': prev_hash,
        'created_at': created_at,
        'actor': actor,
        'action': action,
        'target': target,
        'payload': payload,
    }
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _actor_identity(actor_or_label):
    if isinstance(actor_or_label, str):
        if not actor_or_label.strip():
            raise ValueError('A non-human actor label cannot be empty')
        return None, actor_or_label
    user = getattr(actor_or_label, 'user', None)
    if user is None and getattr(actor_or_label, 'is_anonymous', False):
        return None, 'anonymous'
    if user is None and getattr(actor_or_label, '_meta', None) is not None:
        user = actor_or_label
    if user is None or getattr(user, 'pk', None) is None:
        raise ValueError('actor_or_label must be an authenticated actor, user, or label string')
    return user, ''


def _target_identity(target):
    if isinstance(target, dict):
        target_type = target.get('target_type', target.get('type'))
        target_id = target.get('target_id', target.get('id'))
    elif isinstance(target, (tuple, builtins.list)) and len(target) == 2:
        target_type, target_id = target
    elif getattr(target, '_meta', None) is not None:
        target_type, target_id = target._meta.label_lower, target.pk
    else:
        raise ValueError('target must be a model instance, (type, id), or target mapping')
    if target_type is None or target_id is None:
        raise ValueError('target must include both a type and id')
    return str(target_type), str(target_id)


def _head_for_update():
    connection = connections['default']
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [POSTGRES_ADVISORY_LOCK_KEY])
    else:
        # SQLite does not implement SELECT FOR UPDATE, but this is the portable
        # row-lock path used on databases that do.
        pass
    head, _ = AuditChainHead.objects.get_or_create(
        pk=1, defaults={'seq': 0, 'head_hash': GENESIS_HASH},
    )
    if connection.vendor != 'postgresql':
        head = AuditChainHead.objects.select_for_update().get(pk=1)
    else:
        head = AuditChainHead.objects.select_for_update().get(pk=1)
    return head


def record(actor_or_label=None, action=None, target=None, payload=None, *, actor=None):
    """Append one row inside the caller's transaction and advance the chain head."""
    if actor_or_label is None:
        actor_or_label = actor
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError('audit.record() must run inside transaction.atomic()')
    if not isinstance(action, str) or not action:
        raise ValueError('action must be a non-empty string')
    if not isinstance(payload, dict):
        raise TypeError('payload must be a JSON object')
    # Validate serializability and reject NaN/Infinity before locking the chain.
    canonical_json_bytes(payload)
    actor_user, actor_label = _actor_identity(actor_or_label)
    target_type, target_id = _target_identity(target)

    head = _head_for_update()
    seq = head.seq + 1
    created_at = timezone.now().isoformat()
    actor_value = {'user_id': actor_user.pk if actor_user is not None else None,
                   'label': actor_label or None}
    target_value = {'type': target_type, 'id': target_id}
    digest = _entry_hash(
        seq=seq, prev_hash=head.head_hash, created_at=created_at,
        actor=actor_value, action=action, target=target_value, payload=payload,
    )
    entry = AuditLogEntry.objects.create(
        seq=seq,
        actor_user=actor_user,
        actor_label=actor_label,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        created_at=created_at,
        prev_hash=head.head_hash,
        entry_hash=digest,
    )
    head.seq = seq
    head.head_hash = digest
    head.save(update_fields=['seq', 'head_hash'])
    return entry


def _entry_parts(entry):
    return {
        'seq': entry.seq,
        'prev_hash': entry.prev_hash,
        'created_at': entry.created_at,
        'actor': {
            'user_id': entry.actor_user_id,
            'label': entry.actor_label or None,
        },
        'action': entry.action,
        'target': {'type': entry.target_type, 'id': entry.target_id},
        'payload': entry.payload,
    }


def verify_chain():
    """Return (valid, first_bad_seq, stored_head_hash) after verifying every link."""
    head = AuditChainHead.objects.filter(pk=1).first()
    expected_prev = GENESIS_HASH
    expected_seq = 1
    entries = AuditLogEntry.objects.order_by('seq').iterator()
    for entry in entries:
        if entry.seq != expected_seq:
            return False, expected_seq, head.head_hash if head else GENESIS_HASH
        if entry.prev_hash != expected_prev:
            return False, entry.seq, head.head_hash if head else GENESIS_HASH
        try:
            actual_hash = hashlib.sha256(canonical_json_bytes(_entry_parts(entry))).hexdigest()
        except (TypeError, ValueError):
            return False, entry.seq, head.head_hash if head else GENESIS_HASH
        if actual_hash != entry.entry_hash:
            return False, entry.seq, head.head_hash if head else GENESIS_HASH
        expected_prev = entry.entry_hash
        expected_seq += 1

    final_seq = expected_seq - 1
    stored_hash = head.head_hash if head else GENESIS_HASH
    if head is None:
        return (final_seq == 0, None if final_seq == 0 else 1, stored_hash)
    if head.seq != final_seq:
        return False, min(head.seq, final_seq) + 1, stored_hash
    if head.head_hash != expected_prev:
        return False, max(1, final_seq), stored_hash
    return True, None, stored_hash


def export_chain():
    """Export an offline-verifiable JSON document, including the stored head."""
    head = AuditChainHead.objects.filter(pk=1).first()
    document = {
        'genesis_hash': GENESIS_HASH,
        'entries': [
            {**_entry_parts(entry), 'entry_hash': entry.entry_hash}
            for entry in AuditLogEntry.objects.order_by('seq')
        ],
        'head': {
            'seq': head.seq if head else 0,
            'hash': head.head_hash if head else GENESIS_HASH,
        },
    }
    return json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def list(actor, page=1, page_size=20):
    if not (actor.is_organizer or getattr(actor, 'is_site_admin', False)):
        raise PermissionDenied
    page, page_size = int(page), int(page_size)
    if page < 1 or page_size < 1:
        raise ValueError('page and page_size must be positive integers')
    page_size = min(page_size, 200)
    paginator = Paginator(AuditLogEntry.objects.select_related('actor_user').order_by('-seq'), page_size)
    selected = paginator.get_page(page)
    return {
        'results': builtins.list(selected.object_list),
        'page': selected.number,
        'page_size': page_size,
        'total': paginator.count,
        'pages': paginator.num_pages,
    }


def verify(actor):
    if not (actor.is_organizer or getattr(actor, 'is_site_admin', False)):
        raise PermissionDenied
    return verify_chain()
