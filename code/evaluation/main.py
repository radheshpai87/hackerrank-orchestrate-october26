"""
Evaluation Runner for Ghost Data Still Exists.
Computes case-level, step-level, field-level, and sequence accuracy against public samples
and evaluates custom participant test cases.
"""

import os
import sys
import csv
import json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from code.auditor import DeletionAuditor


def evaluate():
    dataset_dir = os.path.join(REPO_ROOT, "dataset")
    auditor = DeletionAuditor(dataset_dir)

    sample_reqs_path = os.path.join(dataset_dir, "sample_deletion_requests.csv")
    sample_outs_path = os.path.join(dataset_dir, "sample_output.csv")

    with open(sample_reqs_path, mode='r', encoding='utf-8') as f:
        sample_reqs = list(csv.DictReader(f))

    with open(sample_outs_path, mode='r', encoding='utf-8') as f:
        sample_outs = {r['case_id']: (r['deletion_status'], json.loads(r['steps_json'])) for r in csv.DictReader(f)}

    correct_status = 0
    sequence_matches = 0
    total_steps = 0
    field_matches = {'phase': 0, 'system_id': 0, 'resource_id': 0, 'operation': 0, 'state': 0}

    for req in sample_reqs:
        cid = req['case_id']
        res = auditor.audit_case(req)
        exp_status, exp_steps = sample_outs[cid]

        if res.deletion_status == exp_status:
            correct_status += 1

        min_len = min(len(res.steps), len(exp_steps))
        all_step_matched = (len(res.steps) == len(exp_steps))
        for i in range(min_len):
            ps = res.steps[i]
            es = exp_steps[i]
            total_steps += 1
            m_phase = (ps.phase == es['phase'])
            m_sys = (ps.system_id == es['system_id'])
            m_res = (ps.resource_id == es['resource_id'])
            m_op = (ps.operation == es['operation'])
            m_st = (ps.state == es['state'])
            if m_phase: field_matches['phase'] += 1
            if m_sys: field_matches['system_id'] += 1
            if m_res: field_matches['resource_id'] += 1
            if m_op: field_matches['operation'] += 1
            if m_st: field_matches['state'] += 1
            if not (m_phase and m_sys and m_res and m_op and m_st):
                all_step_matched = False

        if all_step_matched and min_len == len(exp_steps):
            sequence_matches += 1

    print("=== EVALUATION BENCHMARK RESULTS ===")
    print(f"Sample Requests Evaluated : {len(sample_reqs)}")
    print(f"Case-Level Status Accuracy: {correct_status}/{len(sample_reqs)} ({correct_status/len(sample_reqs)*100:.1f}%)")
    print(f"Exact Sequence Accuracy   : {sequence_matches}/{len(sample_reqs)} ({sequence_matches/len(sample_reqs)*100:.1f}%)")
    print(f"Compared Step Count       : {total_steps}")
    for k, v in field_matches.items():
        print(f"Field Accuracy [{k:11}]: {v}/{total_steps} ({v/total_steps*100:.1f}%)")


if __name__ == "__main__":
    evaluate()
