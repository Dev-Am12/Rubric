import json
import os
import subprocess
import sys
from pathlib import Path

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from accounts.actors import Actor, PermissionDenied
from accounts.models import EventMembership, EventRole, User
from audit.models import AuditChainHead, AuditLogEntry
from events.models import Event
from services import audit as audit_service


class AuditChainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(
            slug='audit-test-event', name='Audit Test Event',
            submissions_close_at=timezone.now(),
        )
        cls.organizer = User.objects.create_user(
            email='audit-organizer@example.org', display_name='Audit Organizer',
        )
        EventMembership.objects.create(event=cls.event, user=cls.organizer, role=EventRole.ORGANIZER)
        cls.organizer_actor = Actor(cls.organizer, cls.event)

    def append(self, index):
        return audit_service.record(
            self.organizer_actor, 'test.append', ('test_target', str(index)), {'index': index},
        )

    def test_links_form_a_valid_chain_and_head_tracks_tail(self):
        with transaction.atomic():
            entries = [self.append(index) for index in range(3)]
        self.assertEqual([entry.seq for entry in entries], [1, 2, 3])
        self.assertEqual(entries[0].prev_hash, audit_service.GENESIS_HASH)
        self.assertEqual(entries[1].prev_hash, entries[0].entry_hash)
        self.assertEqual(entries[2].prev_hash, entries[1].entry_hash)
        self.assertEqual(audit_service.verify_chain(), (True, None, entries[2].entry_hash))
        head = AuditChainHead.objects.get(pk=1)
        self.assertEqual((head.seq, head.head_hash), (3, entries[2].entry_hash))

    def test_raw_sql_tamper_detects_each_entry_at_its_sequence(self):
        with transaction.atomic():
            entries = [self.append(index) for index in range(3)]
        original_payloads = [entry.payload for entry in entries]
        with connection.cursor() as cursor:
            for seq in (1, 2, 3):
                cursor.execute(
                    'UPDATE audit_auditlogentry SET payload = %s WHERE seq = %s',
                    [json.dumps({'tampered': seq}), seq],
                )
                valid, bad_seq, _ = audit_service.verify_chain()
                self.assertFalse(valid)
                self.assertEqual(bad_seq, seq)
                cursor.execute(
                    'UPDATE audit_auditlogentry SET payload = %s WHERE seq = %s',
                    [json.dumps(original_payloads[seq - 1]), seq],
                )
        self.assertEqual(audit_service.verify_chain()[0], True)

    def test_offline_script_accepts_clean_export_and_locates_tamper(self):
        with transaction.atomic():
            [self.append(index) for index in range(3)]
        document = json.loads(audit_service.export_chain())
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_audit_chain.py'
        export_path = Path(__file__).resolve().parent / f'.audit-chain-test-{os.getpid()}.json'
        try:
            export_path.write_text(json.dumps(document), encoding='utf-8')
            clean = subprocess.run(
                [sys.executable, str(script), str(export_path)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertIn(document['head']['hash'], clean.stdout)

            document['entries'][1]['payload']['tampered'] = True
            export_path.write_text(json.dumps(document), encoding='utf-8')
            tampered = subprocess.run(
                [sys.executable, str(script), str(export_path)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(tampered.returncode, 1)
            self.assertIn('seq 2', tampered.stderr)
        finally:
            export_path.unlink(missing_ok=True)

    def test_golden_hash_vector(self):
        digest = audit_service._entry_hash(
            seq=7,
            prev_hash='a' * 64,
            created_at='2026-01-02T03:04:05+00:00',
            actor={'user_id': 12, 'label': None},
            action='test.action',
            target={'type': 'thing', 'id': 'abc'},
            payload={'a': 1, 'z': 'ok'},
        )
        self.assertEqual(digest, 'f465f1a48a5081f01fd5a839d55d8d165e7414cb0255f59d61643a38f36289df')

    def test_nan_payload_is_rejected(self):
        with transaction.atomic():
            with self.assertRaises(ValueError):
                audit_service.record('test', 'test.nan', ('test', 'nan'), {'bad': float('nan')})
        self.assertEqual(AuditLogEntry.objects.count(), 0)

    def test_model_and_queryset_mutations_are_blocked(self):
        with transaction.atomic():
            entry = self.append(1)
        with self.assertRaises(TypeError):
            entry.save()
        with self.assertRaises(TypeError):
            entry.delete()
        with self.assertRaises(TypeError):
            AuditLogEntry.objects.filter(pk=entry.pk).update(action='tampered')
        with self.assertRaises(TypeError):
            AuditLogEntry.objects.filter(pk=entry.pk).delete()

    def test_organizer_list_paginates_and_verify_is_restricted(self):
        with transaction.atomic():
            [self.append(index) for index in range(3)]
        page = audit_service.list(self.organizer_actor, page=2, page_size=2)
        self.assertEqual(page['total'], 3)
        self.assertEqual(page['pages'], 2)
        self.assertEqual([row.seq for row in page['results']], [1])
        self.assertEqual(audit_service.verify(self.organizer_actor)[0], True)
        judge = User.objects.create_user(email='audit-judge@example.org', display_name='Judge')
        with self.assertRaises(PermissionDenied):
            audit_service.list(Actor(judge, self.event))
        with self.assertRaises(PermissionDenied):
            audit_service.verify(Actor(judge, self.event))


class AuditTransactionTests(TransactionTestCase):
    reset_sequences = True

    def test_record_outside_atomic_raises(self):
        with self.assertRaises(RuntimeError):
            audit_service.record('test', 'test.outside', ('test', 'outside'), {})

    def test_rollback_removes_entry_and_does_not_advance_head(self):
        class RollBackNow(Exception):
            pass

        head_before, _ = AuditChainHead.objects.get_or_create(
            pk=1, defaults={'seq': 0, 'head_hash': audit_service.GENESIS_HASH},
        )
        with self.assertRaises(RollBackNow):
            with transaction.atomic():
                audit_service.record('test', 'test.rollback', ('test', 'rollback'), {})
                raise RollBackNow
        head_after = AuditChainHead.objects.get(pk=1)
        self.assertFalse(AuditLogEntry.objects.exists())
        self.assertEqual((head_after.seq, head_after.head_hash), (head_before.seq, head_before.head_hash))
