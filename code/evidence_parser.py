"""
Evidence Parser for Ghost Data Still Exists.
Parses multi-modal evidence files (JSON, SQL, LOG, TXT, PDF, PNG/OCR)
and extracts grounded resource observations with timestamps and evidence IDs.
"""

import os
import glob
import json
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Set


@dataclass
class EvidenceObservation:
    file_id: str
    file_path: str
    origin: str
    captured_at: str
    system_id: str
    resource_id: str
    state: str  # PRESENT, ABSENT, REDACTED, ANONYMIZED, ACTIVE, BLOCKED, DISABLED
    details: Dict[str, Any]
    user_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class EvidenceParser:
    """Loads and parses all evidence files under dataset/evidence/."""

    def __init__(self, dataset_dir: str, identity_resolver):
        self.dataset_dir = dataset_dir
        self.resolver = identity_resolver
        self.manifest: Dict[str, Dict[str, str]] = {}
        self.path_to_file_id: Dict[str, str] = {}
        self.observations: List[EvidenceObservation] = []
        self._load_manifest()

    def _load_manifest(self):
        import csv
        manifest_path = os.path.join(self.dataset_dir, 'evidence_files.csv')
        if os.path.exists(manifest_path):
            with open(manifest_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    fid = row['file_id']
                    fpath = row['file_path']
                    self.manifest[fid] = row
                    norm_path = os.path.normpath(fpath)
                    self.path_to_file_id[norm_path] = fid
                    self.path_to_file_id[fpath] = fid

    def get_file_id(self, file_path: str) -> str:
        rel = os.path.relpath(file_path, self.dataset_dir)
        norm_rel = os.path.normpath(rel)
        if norm_rel in self.path_to_file_id:
            return self.path_to_file_id[norm_rel]
        if rel in self.path_to_file_id:
            return self.path_to_file_id[rel]
        base = os.path.basename(file_path)
        for p, fid in self.path_to_file_id.items():
            if p.endswith(base):
                return fid
        return "evidence_unknown"

    def parse_all(self):
        self.observations = []
        self._parse_json_records()
        self._parse_sql_databases()
        self._parse_logs()
        self._parse_txt_handover()
        self._parse_pdfs()
        self._parse_images()
        return self.observations

    def _resolve_uid(self, uid_candidate: Optional[str], email_candidate: Optional[str], phone_candidate: Optional[str] = None) -> Optional[str]:
        if uid_candidate and uid_candidate in self.resolver.users:
            return uid_candidate
        if email_candidate:
            uid = self.resolver.resolve_user_id_by_email(email_candidate.lower())
            if uid:
                return uid
            # Check if email_candidate is actually a hash
            uid = self.resolver.resolve_user_id_by_hash(email_candidate)
            if uid:
                return uid
        if phone_candidate:
            uid = self.resolver.resolve_user_id_by_phone(phone_candidate)
            if uid:
                return uid
        return None

    def _parse_json_records(self):
        records_dir = os.path.join(self.dataset_dir, 'evidence', 'records')
        for jf in glob.glob(os.path.join(records_dir, '*.json')):
            fid = self.get_file_id(jf)
            file_meta = self.manifest.get(fid, {})
            captured_at = file_meta.get('captured_at', '2026-09-15T12:00:00Z')

            try:
                with open(jf, mode='r', encoding='utf-8') as fp:
                    data = json.load(fp)
            except Exception:
                continue

            # 1. Snapshot bundle structure
            if 'snapshots' in data:
                for snap in data['snapshots']:
                    data_store = snap.get('data_store', '')
                    snap_captured = snap.get('captured_at', captured_at)
                    for rec in snap.get('records', []):
                        rid = rec.get('resource_id')
                        if not rid:
                            continue
                        uid = rec.get('user_id') or rec.get('customer_reference') or rec.get('subject_reference')
                        em = rec.get('email') or rec.get('owner_email') or rec.get('requester_email') or rec.get('customer_email')
                        ph = rec.get('phone') or rec.get('requester_phone')
                        resolved_uid = self._resolve_uid(uid, em, ph)

                        state = "PRESENT"
                        if data_store == 'analytics_platform':
                            if rec.get('user_id') is None and rec.get('email') is None and rec.get('phone') is None:
                                state = "ANONYMIZED"
                            else:
                                state = "PRESENT"
                        elif data_store == 'identity_service':
                            if rec.get('name') is None and rec.get('email') is None and rec.get('phone') is None:
                                state = "REDACTED"
                            else:
                                state = "PRESENT"
                        elif data_store == 'backup_service':
                            if rec.get('restore_allowed') is True:
                                state = "ACTIVE"
                            else:
                                state = "BLOCKED"
                        elif data_store == 'integration_service':
                            if rec.get('enabled') is True or rec.get('last_delivery_status') == 'delivered':
                                state = "ACTIVE"
                            else:
                                state = "DISABLED"
                        elif data_store == 'support_platform':
                            if rec.get('requester_email') is None and rec.get('requester_phone') is None:
                                state = "REDACTED"
                            else:
                                state = "PRESENT"

                        self.observations.append(EvidenceObservation(
                            file_id=fid,
                            file_path=jf,
                            origin=file_meta.get('origin', ''),
                            captured_at=snap_captured,
                            system_id=data_store,
                            resource_id=rid,
                            state=state,
                            details=rec,
                            user_id=resolved_uid,
                            email=em,
                            phone=ph
                        ))

            # 2. Service resource export structure
            elif 'service_exports' in data:
                for sys_name, sys_content in data['service_exports'].items():
                    for cat_name, items in sys_content.items():
                        for rec in items:
                            rid = rec.get('resource_id')
                            if not rid:
                                continue
                            uid = rec.get('customer_reference') or rec.get('subject_reference')
                            em = rec.get('email') or rec.get('owner_email') or rec.get('requester_email') or rec.get('customer_email')
                            if not em and 'hits' in rec:
                                docs = rec['hits'].get('documents', [])
                                if docs:
                                    em = docs[0].get('email')
                            ph = rec.get('phone')
                            resolved_uid = self._resolve_uid(uid, em, ph)

                            state = "PRESENT"
                            if sys_name == 'account_service':
                                if rec.get('status_code') == 404 or rec.get('profile') is None:
                                    state = "ABSENT"
                                else:
                                    state = "PRESENT"
                            elif sys_name == 'analytics_platform':
                                if rec.get('customer_reference') is None and rec.get('email') is None and rec.get('phone') is None:
                                    state = "ANONYMIZED"
                                else:
                                    state = "PRESENT"
                            elif sys_name == 'backup_service':
                                if rec.get('restore_allowed') is True:
                                    state = "ACTIVE"
                                else:
                                    state = "BLOCKED"
                            elif sys_name == 'integration_service':
                                if rec.get('enabled') is True or rec.get('last_delivery_status') == 'delivered':
                                    state = "ACTIVE"
                                else:
                                    state = "DISABLED"
                            elif sys_name == 'search_service':
                                hits = rec.get('hits', {}).get('total', 0)
                                if hits > 0 or rec.get('hits', {}).get('documents'):
                                    state = "PRESENT"
                                else:
                                    state = "ABSENT"
                            elif sys_name == 'support_platform':
                                if rec.get('requester_email') is None and rec.get('requester_phone') is None:
                                    state = "REDACTED"
                                else:
                                    state = "PRESENT"
                            elif sys_name == 'security_service':
                                state = "PRESENT"

                            self.observations.append(EvidenceObservation(
                                file_id=fid,
                                file_path=jf,
                                origin=file_meta.get('origin', ''),
                                captured_at=captured_at,
                                system_id=sys_name,
                                resource_id=rid,
                                state=state,
                                details=rec,
                                user_id=resolved_uid,
                                email=em,
                                phone=ph
                            ))

            # 3. Simple list or records collection
            elif 'records' in data:
                src = data.get('source', '')
                sys_id = 'export_service' if 'export' in src else ('analytics_platform' if 'analytics' in src else 'account_service')
                for rec in data['records']:
                    rid = rec.get('resource_id')
                    if not rid:
                        continue
                    uid = rec.get('user_id') or rec.get('customer_reference')
                    em = rec.get('email') or rec.get('owner_email')
                    ph = rec.get('phone')
                    resolved_uid = self._resolve_uid(uid, em, ph)

                    state = "PRESENT"
                    if sys_id == 'analytics_platform':
                        if rec.get('user_id') is None and rec.get('email') is None and rec.get('phone') is None:
                            state = "ANONYMIZED"
                    elif sys_id == 'export_service':
                        if rec.get('download_available') is False:
                            state = "ABSENT"

                    self.observations.append(EvidenceObservation(
                        file_id=fid,
                        file_path=jf,
                        origin=file_meta.get('origin', ''),
                        captured_at=captured_at,
                        system_id=sys_id,
                        resource_id=rid,
                        state=state,
                        details=rec,
                        user_id=resolved_uid,
                        email=em,
                        phone=ph
                    ))

    def _parse_sql_databases(self):
        db_dir = os.path.join(self.dataset_dir, 'evidence', 'databases')
        for sql in glob.glob(os.path.join(db_dir, '*.sql')):
            fid = self.get_file_id(sql)
            file_meta = self.manifest.get(fid, {})
            captured_at = file_meta.get('captured_at', '2026-09-15T12:00:00Z')

            try:
                with open(sql, mode='r', encoding='utf-8') as fp:
                    lines = fp.readlines()
            except Exception:
                continue

            current_table = ""
            for line in lines:
                m_tbl = re.search(r'CREATE TABLE (\w+)', line)
                if m_tbl:
                    current_table = m_tbl.group(1)

                if 'INSERT INTO' in line:
                    # Check for embedded JSON string in line
                    m_json = re.search(r"'(\{.*?\})'", line)
                    embedded = None
                    if m_json:
                        try:
                            embedded = json.loads(m_json.group(1))
                        except Exception:
                            pass

                    vals = re.findall(r"'([^']*)'", line)
                    if not vals:
                        continue
                    rid = vals[0]
                    sys_id = "account_service"
                    state = "PRESENT"
                    uid = None
                    em = None
                    ph = None

                    if embedded:
                        rid = embedded.get('resource_id', rid)
                        uid = embedded.get('customer_reference') or embedded.get('user_id') or embedded.get('subject_reference')
                        em = embedded.get('email')
                        ph = embedded.get('phone')
                        if embedded.get('account_status') == 'ACTIVE':
                            state = "PRESENT"

                    if 'search' in current_table or rid.startswith('search_'):
                        sys_id = "search_service"
                    elif 'analytics' in current_table or rid.startswith('analytics_'):
                        sys_id = "analytics_platform"
                    elif 'backup' in current_table or rid.startswith('backup_'):
                        sys_id = "backup_service"
                    elif 'support' in current_table or rid.startswith('support_'):
                        sys_id = "support_platform"
                    elif 'security' in current_table or rid.startswith('audit_record_'):
                        sys_id = "security_service"
                    elif 'connector' in current_table or rid.startswith('data_flow_'):
                        sys_id = "integration_service"
                    elif 'export' in current_table or rid.startswith('export_'):
                        sys_id = "export_service"

                    for v in vals[1:]:
                        if v in self.resolver.users:
                            uid = v
                        elif '@' in v:
                            em = v
                            uid = self.resolver.resolve_user_id_by_email(v)
                        elif v.startswith('+'):
                            ph = v
                            uid = self.resolver.resolve_user_id_by_phone(v)
                        elif len(v) == 64:
                            uid = self.resolver.resolve_user_id_by_hash(v)

                    resolved_uid = self._resolve_uid(uid, em, ph)

                    if sys_id == 'backup_service':
                        if '1' in vals:
                            state = "ACTIVE"
                        else:
                            state = "BLOCKED"
                    elif sys_id == 'integration_service':
                        if '1' in vals or 'true' in line.lower():
                            state = "ACTIVE"
                        else:
                            state = "DISABLED"

                    self.observations.append(EvidenceObservation(
                        file_id=fid,
                        file_path=sql,
                        origin=file_meta.get('origin', ''),
                        captured_at=captured_at,
                        system_id=sys_id,
                        resource_id=rid,
                        state=state,
                        details={"table": current_table, "values": vals},
                        user_id=resolved_uid,
                        email=em,
                        phone=ph
                    ))

    def _parse_logs(self):
        logs_dir = os.path.join(self.dataset_dir, 'evidence', 'logs')
        for log in glob.glob(os.path.join(logs_dir, '*.log')):
            fid = self.get_file_id(log)
            file_meta = self.manifest.get(fid, {})
            captured_at = file_meta.get('captured_at', '2026-09-15T12:00:00Z')

            try:
                with open(log, mode='r', encoding='utf-8', errors='ignore') as fp:
                    lines = fp.readlines()
            except Exception:
                continue

            traces: Dict[str, Dict[str, Any]] = {}
            parsed_lines = []

            for line in lines:
                d = {}
                for m in re.finditer(r'([a-zA-Z0-9_]+)=([^\s\"]+|\"[^\"]*\")', line):
                    d[m.group(1)] = m.group(2).strip('\"')
                if not d and line.startswith('{') and line.endswith('}\n'):
                    try:
                        d = json.loads(line)
                    except Exception:
                        pass
                if 'message' in d and '=' in d['message']:
                    for m in re.finditer(r'([a-zA-Z0-9_]+)=([^\s\"]+|\"[^\"]*\")', d['message']):
                        d[m.group(1)] = m.group(2).strip('\"')
                parsed_lines.append(d)

                tid = d.get('trace_id') or d.get('requestId') or d.get('request_id')
                if tid:
                    if tid not in traces:
                        traces[tid] = {}
                    for id_key in ['user_id', 'subject_ref', 'subject_reference', 'customer_reference']:
                        val = d.get(id_key)
                        if val and val.startswith('user_'):
                            traces[tid]['user_id'] = val
                    for em_key in ['email', 'lookup_key', 'match_key', 'matched_value', 'correlation_key', 'owner_key', 'customer_email', 'requester_email', 'subject_key']:
                        val = d.get(em_key)
                        if val:
                            if '@' in val:
                                traces[tid]['email'] = val.lower()
                            elif len(val) == 64:
                                # Email hash
                                uid_from_hash = self.resolver.resolve_user_id_by_hash(val)
                                if uid_from_hash:
                                    traces[tid]['user_id'] = uid_from_hash
                    for ph_key in ['phone', 'requester_phone']:
                        val = d.get(ph_key)
                        if val and ('+' in val or len(val) >= 7):
                            traces[tid]['phone'] = val

            for d in parsed_lines:
                rid = d.get('resource_id')
                if not rid:
                    continue

                event_type = d.get('event', '')
                if event_type.endswith('_started'):
                    continue

                tid = d.get('trace_id') or d.get('requestId') or d.get('request_id')
                t_info = traces.get(tid, {}) if tid else {}

                uid = t_info.get('user_id') or d.get('user_id') or d.get('subject_ref') or d.get('subject_reference')
                em = t_info.get('email') or d.get('email') or d.get('lookup_key') or d.get('correlation_key') or d.get('subject_key')
                ph = t_info.get('phone') or d.get('phone')

                # Check if em or correlation_key is a hash
                corr_key = d.get('correlation_key') or ''
                if len(corr_key) == 64:
                    uid_from_hash = self.resolver.resolve_user_id_by_hash(corr_key)
                    if uid_from_hash:
                        uid = uid_from_hash

                resolved_uid = self._resolve_uid(uid, em, ph)

                srv = d.get('service') or d.get('logger') or ('account_service' if rid.startswith('account_') else ('security_service' if rid.startswith('audit_') else 'search_service'))
                if srv == 'support_replica':
                    srv = 'support_platform'

                state = "PRESENT"
                if d.get('http_status') in ('404', 404) or d.get('rows') in ('0', 0) or d.get('total_hits') in ('0', 0):
                    state = "ABSENT"
                elif srv == 'support_platform':
                    if d.get('rows') in ('1', 1) or d.get('marker_found') in ('false', False):
                        state = "PRESENT"
                    elif d.get('requester_email') is None and d.get('requester_phone') is None and 'rows' not in d:
                        state = "REDACTED"
                    else:
                        state = "PRESENT"
                elif srv == 'analytics_platform':
                    if d.get('rows') in ('1', 1) or d.get('email_opt_in') in (True, 'true'):
                        state = "PRESENT"
                    elif (not em or em == 'null') and (not ph or ph == 'null') and d.get('audience_cohort'):
                        state = "ANONYMIZED"
                    else:
                        state = "PRESENT"
                elif srv == 'security_service':
                    state = "PRESENT"
                elif srv == 'integration_service':
                    if d.get('enabled') in (True, 'true') or d.get('last_delivery_status') == 'delivered':
                        state = "ACTIVE"
                    else:
                        state = "DISABLED"
                elif srv == 'backup_service':
                    if d.get('restore_allowed') in (True, 'true') or d.get('deletion_block') in (False, 'false') or d.get('eligible') in (True, 'true'):
                        state = "ACTIVE"
                    else:
                        state = "BLOCKED"

                self.observations.append(EvidenceObservation(
                    file_id=fid,
                    file_path=log,
                    origin=file_meta.get('origin', ''),
                    captured_at=captured_at,
                    system_id=srv,
                    resource_id=rid,
                    state=state,
                    details=d,
                    user_id=resolved_uid,
                    email=em,
                    phone=ph
                ))

    def _parse_txt_handover(self):
        txt_path = os.path.join(self.dataset_dir, 'evidence', 'records', 'customer_account_handover_20261001.txt')
        if not os.path.exists(txt_path):
            return

        fid = self.get_file_id(txt_path)
        file_meta = self.manifest.get(fid, {})
        captured_at = file_meta.get('captured_at', '2026-10-01T12:00:00Z')

        with open(txt_path, mode='r', encoding='utf-8') as fp:
            for line in fp:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 6:
                    ts = parts[0]
                    sys_id = parts[1]
                    rid = parts[2]
                    cat = parts[3]
                    status_raw = parts[4]
                    ident = parts[5].strip()

                    uid = None
                    em = None
                    if ident in self.resolver.users:
                        uid = ident
                    elif '@' in ident:
                        em = ident
                        uid = self.resolver.resolve_user_id_by_email(ident.lower())

                    state = "PRESENT"
                    if status_raw == 'NOT_FOUND':
                        state = "ABSENT"
                    elif status_raw in ('FOUND', 'IDENTIFIABLE'):
                        state = "PRESENT"
                    elif status_raw == 'ANONYMIZED':
                        state = "ANONYMIZED"
                    elif status_raw == 'ACTIVE':
                        state = "ACTIVE"
                    elif status_raw == 'BLOCKED':
                        state = "BLOCKED"
                    elif status_raw == 'DISABLED':
                        state = "DISABLED"
                    elif status_raw == 'REDACTED':
                        state = "REDACTED"

                    self.observations.append(EvidenceObservation(
                        file_id=fid,
                        file_path=txt_path,
                        origin=file_meta.get('origin', ''),
                        captured_at=captured_at,
                        system_id=sys_id,
                        resource_id=rid,
                        state=state,
                        details={"category": cat, "status": status_raw},
                        user_id=uid,
                        email=em
                    ))

    def _parse_pdfs(self):
        docs_dir = os.path.join(self.dataset_dir, 'evidence', 'documents')
        for pdf in glob.glob(os.path.join(docs_dir, '*.pdf')):
            fid = self.get_file_id(pdf)
            file_meta = self.manifest.get(fid, {})
            captured_at = file_meta.get('captured_at', '2026-09-15T12:00:00Z')

            try:
                res = subprocess.run(['pdftotext', pdf, '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                text = res.stdout
            except Exception:
                continue

            rids = re.findall(r'(support_\d+|export_\d+|account_\d+|ORD-\d+)', text)
            emails = re.findall(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text)
            phones = re.findall(r'(\+\d[\d\s-]{8,}\d)', text)

            for rid in rids:
                if rid.startswith('ORD-'):
                    continue
                sys_id = 'support_platform' if rid.startswith('support_') else ('export_service' if rid.startswith('export_') else 'account_service')
                em = emails[0].lower() if emails else None
                ph = phones[0] if phones else None
                uid = self._resolve_uid(None, em, ph)

                self.observations.append(EvidenceObservation(
                    file_id=fid,
                    file_path=pdf,
                    origin=file_meta.get('origin', ''),
                    captured_at=captured_at,
                    system_id=sys_id,
                    resource_id=rid,
                    state="PRESENT",
                    details={"text_snippet": text[:200]},
                    user_id=uid,
                    email=em,
                    phone=ph
                ))

    def _parse_images(self):
        imgs_dir = os.path.join(self.dataset_dir, 'evidence', 'images')
        cache_path = os.path.join(os.path.dirname(__file__), 'ocr_cache.json')
        ocr_cache = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, mode='r', encoding='utf-8') as f:
                    ocr_cache = json.load(f)
            except Exception:
                pass

        dirty_cache = False
        for img in glob.glob(os.path.join(imgs_dir, '*.png')):
            fid = self.get_file_id(img)
            file_meta = self.manifest.get(fid, {})
            captured_at = file_meta.get('captured_at', '2026-09-15T12:00:00Z')

            text = ocr_cache.get(img)
            if text is None:
                try:
                    res = subprocess.run(['tesseract', img, 'stdout'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
                    text = res.stdout
                    ocr_cache[img] = text
                    dirty_cache = True
                except Exception:
                    continue

            rids = re.findall(r'(account_\d+|support_\d+|search_\d+|analytics_\d+|data_flow_\d+|backup_\d+)', text)
            emails = re.findall(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text)
            phones = re.findall(r'(\+\d[\d\s-]{8,}\d)', text)

            for rid in rids:
                sys_id = 'account_service' if rid.startswith('account_') else ('support_platform' if rid.startswith('support_') else 'search_service')
                em = emails[0].lower() if emails else None
                ph = phones[0] if phones else None
                uid = self._resolve_uid(None, em, ph)

                state = "PRESENT"
                if '404' in text or 'not found' in text.lower():
                    state = "ABSENT"

                self.observations.append(EvidenceObservation(
                    file_id=fid,
                    file_path=img,
                    origin=file_meta.get('origin', ''),
                    captured_at=captured_at,
                    system_id=sys_id,
                    resource_id=rid,
                    state=state,
                    details={"ocr_snippet": text[:200]},
                    user_id=uid,
                    email=em,
                    phone=ph
                ))

        if dirty_cache:
            try:
                with open(cache_path, mode='w', encoding='utf-8') as f:
                    json.dump(ocr_cache, f)
            except Exception:
                pass
