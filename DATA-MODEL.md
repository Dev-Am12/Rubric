# Judging data and fixture provenance

Each event has a default rubric with three equally weighted criteria:
`functionality`, `quality`, and `innovation`. Each imported `scores[]` entry
creates one completed `JudgeAssignment` for its judge/project pair, one
complete `Ballot`, and one `BallotScore` per criterion. The importer keys the
assignment and ballot by their relationship and upserts each criterion score,
so rerunning `seed_fixtures` does not duplicate them.

Fixture score records do not include a judging timestamp. For imported
ballots, `submitted_at` is the timestamp of the import run that last updated
the ballot. It records import provenance only; it does not claim when the
judge actually scored the project. A real judge submission instead records the
submission time.
