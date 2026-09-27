from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from judging.models import NormalizationRun
from services.normalization import build_proof_artifact


class Command(BaseCommand):
    help = 'Write a static raw/normalized/rank-change CSV from a stored normalization run.'

    def add_arguments(self, parser):
        parser.add_argument('run_id', type=int)
        parser.add_argument('--output', required=True, help='Destination CSV file path')

    def handle(self, *args, **options):
        try:
            run_record = NormalizationRun.objects.get(pk=options['run_id'])
        except NormalizationRun.DoesNotExist as exc:
            raise CommandError(f"NormalizationRun {options['run_id']} does not exist") from exc
        output_path = Path(options['output'])
        output_path.write_bytes(build_proof_artifact(run_record))
        self.stdout.write(self.style.SUCCESS(f'Wrote {output_path}'))
