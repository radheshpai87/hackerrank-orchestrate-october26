"""
Identity Resolution Engine for Ghost Data Still Exists.
Resolves both current snapshots and historical identity changes from user_audit_log.csv.
"""

import csv
import os
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, List


@dataclass
class UserIdentity:
    user_id: str
    current_name: str
    current_email: str
    current_phone: str
    email_hash: str
    updated_at: str
    all_names: Set[str] = field(default_factory=set)
    all_emails: Set[str] = field(default_factory=set)
    all_phones: Set[str] = field(default_factory=set)
    all_hashes: Set[str] = field(default_factory=set)


class IdentityResolver:
    """Manages identity graph with historical changes and alias resolution."""

    def __init__(self, identities_path: str, audit_log_path: str):
        self.identities_path = identities_path
        self.audit_log_path = audit_log_path
        self.users: Dict[str, UserIdentity] = {}
        self.email_to_uid: Dict[str, str] = {}
        self.phone_to_uid: Dict[str, str] = {}
        self.name_to_uid: Dict[str, str] = {}
        self.hash_to_uid: Dict[str, str] = {}
        self._load()

    def _load(self):
        # 1. Load current identity snapshots
        if os.path.exists(self.identities_path):
            with open(self.identities_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = row['user_id'].strip()
                    name = row['name'].strip()
                    email = row['email'].strip().lower()
                    phone = row['phone'].strip()
                    ehash = row['email_hash'].strip().lower()
                    updated_at = row['updated_at'].strip()

                    user = UserIdentity(
                        user_id=uid,
                        current_name=name,
                        current_email=email,
                        current_phone=phone,
                        email_hash=ehash,
                        updated_at=updated_at,
                        all_names={name.lower()},
                        all_emails={email},
                        all_phones={phone},
                        all_hashes={ehash} if ehash else set()
                    )
                    self.users[uid] = user
                    self.email_to_uid[email] = uid
                    self.phone_to_uid[phone] = uid
                    self.name_to_uid[name.lower()] = uid
                    if ehash:
                        self.hash_to_uid[ehash] = uid

        # 2. Replay historical identity changes from user_audit_log.csv
        if os.path.exists(self.audit_log_path):
            with open(self.audit_log_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = row['user_id'].strip()
                    field_name = row['field_name'].strip()
                    old_val = row['old_value'].strip()
                    new_val = row['new_value'].strip()

                    if uid not in self.users:
                        continue

                    user = self.users[uid]
                    if field_name == 'email':
                        if old_val:
                            user.all_emails.add(old_val.lower())
                            self.email_to_uid[old_val.lower()] = uid
                        if new_val:
                            user.all_emails.add(new_val.lower())
                            self.email_to_uid[new_val.lower()] = uid
                    elif field_name == 'phone':
                        if old_val:
                            user.all_phones.add(old_val)
                            self.phone_to_uid[old_val] = uid
                        if new_val:
                            user.all_phones.add(new_val)
                            self.phone_to_uid[new_val] = uid
                    elif field_name == 'name':
                        if old_val:
                            user.all_names.add(old_val.lower())
                            self.name_to_uid[old_val.lower()] = uid
                        if new_val:
                            user.all_names.add(new_val.lower())
                            self.name_to_uid[new_val.lower()] = uid
                    elif field_name == 'email_hash':
                        if old_val:
                            user.all_hashes.add(old_val.lower())
                            self.hash_to_uid[old_val.lower()] = uid
                        if new_val:
                            user.all_hashes.add(new_val.lower())
                            self.hash_to_uid[new_val.lower()] = uid

    def resolve_user_id_by_email(self, email: str) -> Optional[str]:
        if not email:
            return None
        return self.email_to_uid.get(email.strip().lower())

    def resolve_user_id_by_phone(self, phone: str) -> Optional[str]:
        if not phone:
            return None
        return self.phone_to_uid.get(phone.strip())

    def resolve_user_id_by_hash(self, email_hash: str) -> Optional[str]:
        if not email_hash:
            return None
        return self.hash_to_uid.get(email_hash.strip().lower())

    def get_user(self, user_id: str) -> Optional[UserIdentity]:
        return self.users.get(user_id)
