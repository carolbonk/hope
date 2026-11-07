"""Manual live smoke test against the public Grants.gov API (not run in CI).

uv run python services/ingestion/scripts/grants_gov_smoke.py "youth mentoring" --rows 3
"""

from __future__ import annotations

import argparse

from hope_ingestion.connectors.base import Cursor, SavedSearch
from hope_ingestion.connectors.grants_gov import GrantsGovConnector
from hope_ingestion.testing import offline_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keywords", nargs="?", default="youth mentoring")
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--parse", action="store_true", help="download and parse documents")
    args = parser.parse_args()

    connector = GrantsGovConnector()
    print("health:", connector.health().model_dump())
    query = SavedSearch(keywords=args.keywords.split(), page_size=args.rows, max_records=args.rows)
    if args.parse:
        pipeline, pillar = offline_pipeline()
        results, cursor = pipeline.run(connector, query)
        for result in results:
            opp = result.opportunity
            print(result.status, opp.source.source_id if opp else None, opp.title if opp else None)
            for issue in result.blocking:
                print("   blocking:", issue.field, issue.reason)
        print("events:", [e.event_type.value for e in pillar.log], "cursor:", cursor.position)
        return
    for record in connector.discover(Cursor(), query):
        facts = connector.facts(record)
        print(record.source_id, "|", facts.title)
        print("   due:", facts.application_due, "ceiling:", facts.award_ceiling, "aln:", facts.aln)
        print("   artifacts:", [ref.url for ref in connector.fetch_artifacts(record)])


if __name__ == "__main__":
    main()
