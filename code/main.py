"""
Main Runner for Ghost Data Still Exists Deletion Audit Agent.
Generates output.csv compliant with HackerRank Orchestrate (October 2026) specification.
"""

import os
import sys
import csv
import json
import argparse
from typing import List

# Ensure repository root is on Python path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from code.auditor import DeletionAuditor
from code.models import CaseAuditResult


def parse_case_number(case_id: str) -> int:
    try:
        return int(case_id.replace('case_', ''))
    except Exception:
        return 999999


def run_audit(dataset_dir: str, output_csv_path: str):
    print(f"[*] Initializing DeletionAuditor with dataset at: {dataset_dir}")
    auditor = DeletionAuditor(dataset_dir)

    requests_path = os.path.join(dataset_dir, "deletion_requests.csv")
    if not os.path.exists(requests_path):
        print(f"[!] Error: {requests_path} not found.")
        sys.exit(1)

    print(f"[*] Loading evaluation requests from: {requests_path}")
    with open(requests_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        requests = list(reader)

    print(f"[*] Processing {len(requests)} deletion audit cases...")
    results: List[CaseAuditResult] = []
    for idx, req in enumerate(requests, 1):
        res = auditor.audit_case(req)
        results.append(res)
        if idx % 100 == 0 or idx == len(requests):
            print(f"    Processed {idx}/{len(requests)} cases...")

    # Sort strictly by case_id (numeric order)
    results.sort(key=lambda r: parse_case_number(r.case_id))

    print(f"[*] Writing {len(results)} rows to {output_csv_path}...")
    with open(output_csv_path, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for r in results:
            steps_data = [s.to_dict() for s in r.steps]
            writer.writerow([r.case_id, r.deletion_status, json.dumps(steps_data, separators=(',', ':'))])

    print(f"[+] Output written successfully to: {output_csv_path}")

    # Display summary statistics
    status_counts = {}
    for r in results:
        status_counts[r.deletion_status] = status_counts.get(r.deletion_status, 0) + 1
    print("\nSummary of Predictions:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status:16}: {count:4d} ({count/len(results)*100:.1f}%)")


def run_evaluation(dataset_dir: str):
    print(f"[*] Running Evaluation against sample dataset...")
    auditor = DeletionAuditor(dataset_dir)

    sample_reqs_path = os.path.join(dataset_dir, "sample_deletion_requests.csv")
    sample_outs_path = os.path.join(dataset_dir, "sample_output.csv")

    with open(sample_reqs_path, mode='r', encoding='utf-8') as f:
        sample_reqs = list(csv.DictReader(f))

    with open(sample_outs_path, mode='r', encoding='utf-8') as f:
        sample_outs = {r['case_id']: (r['deletion_status'], json.loads(r['steps_json'])) for r in csv.DictReader(f)}

    correct_status = 0
    exact_steps = 0
    total_expected_steps = 0
    total_matched_steps = 0

    print(f"{'Case ID':8} | {'Predicted':12} | {'Expected':12} | {'Status Match':12} | {'Pred Steps':10} | {'Exp Steps':10}")
    print("-" * 75)
    for req in sample_reqs:
        cid = req['case_id']
        res = auditor.audit_case(req)
        exp_status, exp_steps = sample_outs[cid]

        st_match = (res.deletion_status == exp_status)
        if st_match:
            correct_status += 1

        pred_tuples = {(s.phase, s.system_id, s.resource_id, s.operation, s.state) for s in res.steps}
        exp_tuples = {(s['phase'], s['system_id'], s['resource_id'], s['operation'], s['state']) for s in exp_steps}
        matched_tuples = pred_tuples.intersection(exp_tuples)

        total_expected_steps += len(exp_tuples)
        total_matched_steps += len(matched_tuples)

        if pred_tuples == exp_tuples:
            exact_steps += 1

        print(f"{cid:8} | {res.deletion_status:12} | {exp_status:12} | {str(st_match):12} | {len(res.steps):10d} | {len(exp_steps):10d}")

    print("-" * 75)
    print(f"Case-level Status Accuracy : {correct_status}/{len(sample_reqs)} ({correct_status/len(sample_reqs)*100:.1f}%)")
    print(f"Exact Step Match Accuracy  : {exact_steps}/{len(sample_reqs)} ({exact_steps/len(sample_reqs)*100:.1f}%)")
    print(f"Step Precision / Recall    : {total_matched_steps}/{total_expected_steps} ({total_matched_steps/total_expected_steps*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists Deletion Audit Agent")
    parser.add_argument("--dataset", default="dataset", help="Path to dataset directory")
    parser.add_argument("--output", default="output.csv", help="Path to write output.csv")
    parser.add_argument("--eval", action="store_true", help="Run sample evaluation")

    args = parser.parse_args()

    if args.eval:
        run_evaluation(args.dataset)
    else:
        run_audit(args.dataset, args.output)


if __name__ == "__main__":
    main()
