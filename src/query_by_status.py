import argparse
import json

from src.db import get_jobs_by_status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status", required=True)
    args = parser.parse_args()

    jobs = get_jobs_by_status(run_id=args.run_id, status=args.status)
    ids = [j["id"] for j in jobs]

    print(f"ids_json={json.dumps(ids)}")


if __name__ == "__main__":
    main()