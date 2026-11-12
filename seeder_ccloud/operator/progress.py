"""Keep reconciliation progress tied to the desired seed configuration."""

import hashlib
import json

import kopf


class SeedProgressStorage(kopf.AnnotationsProgressStorage):
    @staticmethod
    def spec_hash(body):
        spec = dict(body.get('spec', {}))
        # Some existing handlers put runtime information in spec.duration.
        # Status/metadata updates must not restart reconciliation.
        spec.pop('duration', None)
        serialized = json.dumps(spec, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    def fetch(self, *, key, body):
        record = super().fetch(key=key, body=body)
        if record is None:
            return None
        # Old operators did not record which input a handler had processed.
        # Reconcile those checkpoints once to recover already stuck seeds.
        if record.pop('seed_spec_hash', None) != self.spec_hash(body):
            return None
        return record

    def store(self, *, key, record, body, patch):
        # Strip the hash in fetch() so Kopf's unchanged-progress comparison
        # remains effective. Never mutate the record owned by the framework.
        record = dict(record, seed_spec_hash=self.spec_hash(body))
        super().store(key=key, record=record, body=body, patch=patch)
