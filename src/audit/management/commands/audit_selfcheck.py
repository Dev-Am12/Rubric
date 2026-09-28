from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connections, transaction

from audit.models import AuditLogEntry
from services.audit import record, verify_chain


class Command(BaseCommand):
    help = 'Stress the audit hash chain with concurrent appends, then verify it.'

    def add_arguments(self, parser):
        parser.add_argument('--threads', type=int, required=True)
        parser.add_argument('--entries', type=int, required=True)

    def handle(self, *args, **options):
        threads = options['threads']
        entries = options['entries']
        if threads < 1 or entries < 1:
            raise CommandError('--threads and --entries must both be positive')
        if connections['default'].vendor != 'postgresql':
            raise CommandError('audit_selfcheck concurrency run requires PostgreSQL')

        def write_worker(worker_id):
            close_old_connections()
            try:
                for index in range(entries):
                    with transaction.atomic():
                        record(
                            'audit_selfcheck',
                            'audit.selfcheck',
                            ('audit_selfcheck', f'{worker_id}:{index}'),
                            {'worker': worker_id, 'index': index},
                        )
            finally:
                connections['default'].close()

        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = [pool.submit(write_worker, worker_id) for worker_id in range(threads)]
            for future in futures:
                future.result()

        ok, first_bad_seq, head_hash = verify_chain()
        count = AuditLogEntry.objects.count()
        distinct_seq_count = AuditLogEntry.objects.values('seq').distinct().count()
        first_seq = AuditLogEntry.objects.order_by('seq').values_list('seq', flat=True).first()
        last_seq = AuditLogEntry.objects.order_by('-seq').values_list('seq', flat=True).first()
        gapless = (count == 0 and first_seq is None) or (first_seq == 1 and last_seq == count)
        no_duplicates = count == distinct_seq_count
        self.stdout.write(
            f'audit_selfcheck: threads={threads} entries_per_thread={entries} '
            f'added={threads * entries} total_entries={count} '
            f'valid={ok} first_bad_seq={first_bad_seq} gapless={gapless} '
            f'no_duplicates={no_duplicates} head_hash={head_hash}'
        )
        if not ok or not gapless or not no_duplicates:
            raise CommandError('audit chain self-check failed')
