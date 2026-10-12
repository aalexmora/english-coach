"""Named concurrency tokens and compact, recoverable MCP errors."""
import json


def version_alias(named, legacy, name, required=False):
    if named is not None and legacy is not None and named != legacy:
        raise ValueError(f'{name} and deprecated expected_version disagree')
    value = named if named is not None else legacy
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError(f'{name} must be a positive integer')
    if required and value is None:
        raise ValueError(f'{name} is required')
    return value


class VersionConflict(ValueError):
    def __init__(self, target, expected, state):
        field = target + '_version'
        self.payload = dict(
            error='version_conflict', saved=False, object=target,
            expected_version=expected, current_version=state[field],
            session_id=state['session_id'],
            session_version=state['session_version'], coach_version=state['coach_version'],
            phase=state['phase'], current_item_id=state['current_item_id'],
            retry={'expected_'+field: state[field]},
            recovery='Nothing was committed. Keep the same idempotency key and observations. '
                     'Replace the conflicting token with the named retry field, removing its deprecated '
                     'alias if that tool uses one; keep other version fields. '
                     'For a session conflict, retry once with expected_session_version=current_version '
                     'after checking current_item_id. A Coach conflict needs state review through '
                     'get_english_session_state; never blindly repeat a plan transition.')
        super().__init__('Version conflict: ' + json.dumps(self.payload, ensure_ascii=False))
