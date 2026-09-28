import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from django.db import connection, connections, DatabaseError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from accounts.actors import Actor, PermissionDenied
from accounts.models import AuthToken, EventMembership, EventRole, User
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
        _, cls.organizer_token = AuthToken.create_token(cls.organizer)

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

    def test_audit_pagination_boundaries_api_and_html_views(self):
        """
        Audit pagination boundaries: page/page_size < 1 or non-numeric must never 500.
        API returns 400 {"error":"invalid_parameters","detail":...};
        HTML view clamps to sane defaults (page>=1, 1<=page_size<=200).
        Tests for 0, negative, non-numeric, huge.
        """
        client = Client()
        auth_header = {'HTTP_AUTHORIZATION': f'Bearer {self.organizer_token}'}

        # 1. API view boundary cases
        # Non-numeric
        for bad_param in [{'page': 'abc'}, {'page_size': 'xyz'}, {'page': 'foo', 'page_size': 'bar'}]:
            res = client.get('/api/v1/organizer/audit-log', bad_param, **auth_header)
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json().get('error'), 'invalid_parameters')

        # 0 (less than 1)
        for zero_param in [{'page': 0}, {'page_size': 0}, {'page': 0, 'page_size': 0}]:
            res = client.get('/api/v1/organizer/audit-log', zero_param, **auth_header)
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json().get('error'), 'invalid_parameters')

        # Negative
        for neg_param in [{'page': -5}, {'page_size': -10}, {'page': -1, 'page_size': -20}]:
            res = client.get('/api/v1/organizer/audit-log', neg_param, **auth_header)
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json().get('error'), 'invalid_parameters')

        # Huge
        res_huge = client.get('/api/v1/organizer/audit-log', {'page': 999999999, 'page_size': 999999999}, **auth_header)
        self.assertEqual(res_huge.status_code, 200)
        data = res_huge.json()
        self.assertEqual(data.get('entries'), [])
        self.assertEqual(data.get('page_size'), 200)  # clamped to 200

        # 2. HTML view boundary cases (must clamp to sane defaults, never 500)
        # Non-numeric
        res_html_nonnum = client.get('/organizer/audit-log', {'page': 'abc', 'page_size': 'xyz'}, **auth_header)
        self.assertEqual(res_html_nonnum.status_code, 200)
        self.assertContains(res_html_nonnum, 'Audit Log')

        # 0
        res_html_zero = client.get('/organizer/audit-log', {'page': 0, 'page_size': 0}, **auth_header)
        self.assertEqual(res_html_zero.status_code, 200)
        self.assertContains(res_html_zero, 'Audit Log')

        # Negative
        res_html_neg = client.get('/organizer/audit-log', {'page': -5, 'page_size': -10}, **auth_header)
        self.assertEqual(res_html_neg.status_code, 200)
        self.assertContains(res_html_neg, 'Audit Log')

        # Huge
        res_html_huge = client.get('/organizer/audit-log', {'page': 999999999, 'page_size': 999999999}, **auth_header)
        self.assertEqual(res_html_huge.status_code, 200)
        self.assertContains(res_html_huge, 'Audit Log')


class AuditTransactionTestCase(TransactionTestCase):
    """Shared base class for TransactionTestCase tests touching audit tables.

    On Postgres only, disables the truncate trigger before flush and re-enables it after.
    The production trigger itself must not change.
    """

    def _fixture_teardown(self):
        for db_name in self._databases_names(include_mirrors=False):
            conn = connections[db_name]
            if conn.vendor == 'postgresql':
                with conn.cursor() as cursor:
                    cursor.execute('ALTER TABLE audit_auditlogentry DISABLE TRIGGER audit_log_entry_no_truncate;')
        try:
            super()._fixture_teardown()
        finally:
            for db_name in self._databases_names(include_mirrors=False):
                conn = connections[db_name]
                if conn.vendor == 'postgresql':
                    with conn.cursor() as cursor:
                        cursor.execute('ALTER TABLE audit_auditlogentry ENABLE TRIGGER audit_log_entry_no_truncate;')


class AuditTransactionTests(AuditTransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        self.event = Event.objects.create(
            slug='audit-tx-event', name='Audit Tx Event',
            submissions_close_at=timezone.now(),
        )
        self.organizer = User.objects.create_user(
            email='audit-tx-organizer@example.org', display_name='Audit Tx Organizer',
        )
        EventMembership.objects.create(event=self.event, user=self.organizer, role=EventRole.ORGANIZER)
        self.organizer_actor = Actor(self.organizer, self.event)

    def append(self, index):
        return audit_service.record(
            self.organizer_actor, 'test.append', ('test_target', str(index)), {'index': index},
        )

    @unittest.skipUnless(connection.vendor == 'postgresql', 'PostgreSQL-only trigger immutability test')
    def test_postgres_immutability_trigger_rejects_raw_mutations(self):
        with transaction.atomic():
            entry = self.append(1)
        with connection.cursor() as cursor:
            # 1. Reject raw UPDATE
            with self.assertRaises(DatabaseError) as ctx_update:
                with transaction.atomic():
                    cursor.execute(
                        'UPDATE audit_auditlogentry SET payload = %s WHERE seq = %s',
                        [json.dumps({'tampered': True}), entry.seq],
                    )
            self.assertIn('audit log entries are immutable', str(ctx_update.exception))

            # 2. Reject raw DELETE
            with self.assertRaises(DatabaseError) as ctx_delete:
                with transaction.atomic():
                    cursor.execute('DELETE FROM audit_auditlogentry WHERE seq = %s', [entry.seq])
            self.assertIn('audit log entries are immutable', str(ctx_delete.exception))

            # 3. Reject raw TRUNCATE
            with self.assertRaises(DatabaseError) as ctx_truncate:
                with transaction.atomic():
                    cursor.execute('TRUNCATE TABLE audit_auditlogentry')
            self.assertIn('audit log entries are immutable', str(ctx_truncate.exception))

    def test_raw_sql_tamper_detects_each_entry_at_its_sequence(self):
        with transaction.atomic():
            entries = [self.append(index) for index in range(3)]
        original_payloads = [entry.payload for entry in entries]
        is_postgres = connection.vendor == 'postgresql'
        triggers_disabled = False

        with connection.cursor() as cursor:
            if is_postgres:
                try:
                    cursor.execute('ALTER TABLE audit_auditlogentry DISABLE TRIGGER USER;')
                    triggers_disabled = True
                except Exception as exc:
                    self.skipTest(f'Missing privilege to disable triggers on audit_auditlogentry: {exc}')

            try:
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
            finally:
                if triggers_disabled:
                    cursor.execute('ALTER TABLE audit_auditlogentry ENABLE TRIGGER USER;')

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
