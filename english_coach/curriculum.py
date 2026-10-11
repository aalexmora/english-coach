"""Versioned curriculum input, read through the host MemoryAPI only."""
import json
from copy import deepcopy

KEY = 'english-course-program'


def read_program(memory):
    doc = memory.get(KEY)
    if doc is None:
        return None
    try:
        value = doc['value']
        if len(json.dumps(value)) > 60000 or value['schema'] != 'english_course_program_v1':
            raise ValueError('Invalid program')
        stages = value['stages']
        sources = value['source_analysis']
        ids = [s['id'] for s in stages]
        source_ids = [s['id'] for s in sources]
        if (not 1 <= len(stages) <= 20 or not 1 <= len(sources) <= 20
                or len(set(ids)) != len(ids) or len(set(source_ids)) != len(source_ids)
                or value['teaching_state']['current_stage'] not in ids):
            raise ValueError('Invalid program')
        for stage in stages:
            if not set(stage['source_ids']) <= set(source_ids):
                raise ValueError('Invalid source reference')
        return deepcopy(doc)
    except (KeyError, TypeError, ValueError):
        return dict(key=KEY, version=doc['version'], invalid=True,
                    error='Invalid course program; correct the source before review')


def check_attribution(snapshot, review):
    program = snapshot.get('course_program')
    attribution = review.get('curriculum')
    if not program:
        if attribution is not None:
            raise ValueError('No curriculum supplied')
        return
    if program.get('invalid'):
        raise ValueError('Invalid course program')
    value = program['value']
    stage_id = value['teaching_state']['current_stage']
    stage = next(s for s in value['stages'] if s['id'] == stage_id)
    if (not attribution or attribution['document_version'] != program['version']
            or attribution['stage_id'] != stage_id
            or not attribution['source_ids']
            or not set(attribution['source_ids']) <= set(stage['source_ids'])):
        raise ValueError('Curriculum attribution mismatch')
