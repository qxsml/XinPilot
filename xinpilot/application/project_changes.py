"""Content comparison for project edits; independent of UI and persistence."""
import hashlib
import json


def fingerprint(state):
    def canonical(value):
        if isinstance(value, dict):
            # Controllers may key reaction records by tuples, while archives
            # use lists. Preserve keys without requiring JSON-compatible keys.
            pairs = [[canonical(k), canonical(v)] for k, v in value.items()]
            pairs.sort(key=lambda pair: json.dumps(pair[0], ensure_ascii=False, default=str))
            return {'mapping': pairs}
        if isinstance(value, (list, tuple)):
            return [canonical(item) for item in value]
        return value
    encoded = json.dumps(canonical(state), ensure_ascii=False, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


class ProjectChanges:
    def __init__(self, state):
        self.mark_saved(state)

    def mark_saved(self, state):
        self.baseline = fingerprint(state)

    def changed(self, state):
        return fingerprint(state) != self.baseline
