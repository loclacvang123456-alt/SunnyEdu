"""Pure calculations. Callers provide only eligible published current attempts."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal('0.01')
SKILLS = {'READING','LISTENING','WRITING','SPEAKING'}

@dataclass(frozen=True)
class Evidence:
    attempt_id: str
    skill: str
    points: Decimal
    maximum: Decimal
    difficulty: str
    topics: frozenset[str]

    def __post_init__(self):
        if self.skill not in SKILLS or self.maximum <= 0 or self.points < 0 or self.points > self.maximum:
            raise ValueError('Invalid evidence')


def skill_summary(rows, skill):
    if skill not in SKILLS:
        raise ValueError('Unknown skill')
    rows = [r for r in rows if r.skill == skill]
    if not rows:
        return {'percent': None, 'label': None, 'questions': 0, 'attempts': 0}
    percent = (sum((r.points for r in rows), Decimal(0)) * 100 / sum((r.maximum for r in rows), Decimal(0))).quantize(CENT, rounding=ROUND_HALF_UP)
    attempts = len({r.attempt_id for r in rows})
    enough = attempts >= 2 and len(rows) >= (5 if skill in {'READING','LISTENING'} else 2)
    label = None if not enough else ('NEEDS_SUPPORT' if percent < 50 else 'REINFORCING' if percent < 75 else 'GOOD')
    return {'percent': percent, 'label': label, 'questions': len(rows), 'attempts': attempts}


def skill_trend(current, previous, skill):
    if skill not in SKILLS:
        raise ValueError('Unknown skill')
    current = [r for r in current if r.skill == skill]
    previous = [r for r in previous if r.skill == skill]
    keys = lambda rows: {(r.difficulty, topic) for r in rows for topic in r.topics}
    common = keys(current) & keys(previous)
    include = lambda r: any((r.difficulty, topic) in common for topic in r.topics)
    recent = skill_summary([r for r in current if include(r)], skill)
    earlier = skill_summary([r for r in previous if include(r)], skill)
    if recent['label'] is None or earlier['label'] is None:
        return {'trend': None, 'current': recent, 'previous': earlier}
    delta = recent['percent'] - earlier['percent']
    return {'trend': 'UP' if delta >= 10 else 'DOWN' if delta <= -10 else 'STABLE', 'current': recent, 'previous': earlier}


def rank_results(member_scores, assignment_count):
    """Mapping member id -> [(points, maximum), ...] in fixed assignment order.

    None denotes a missing published result. Input list length must match the cohort.
    """
    if assignment_count < 1:
        raise ValueError('At least one assignment is required')
    results = {}
    for member, scores in member_scores.items():
        if len(scores) != assignment_count:
            raise ValueError('Scores must match the fixed assignment list')
        if any(score is None for score in scores):
            results[member] = {'status':'INCOMPLETE', 'score':None, 'rank':None}
            continue
        percentages = []
        for points, maximum in scores:
            points, maximum = Decimal(points), Decimal(maximum)
            if maximum <= 0 or points < 0 or points > maximum:
                raise ValueError('Invalid score')
            percentages.append(points * 100 / maximum)
        score = (sum(percentages, Decimal(0)) / assignment_count).quantize(CENT, rounding=ROUND_HALF_UP)
        results[member] = {'status':'RANKED', 'score':score, 'rank':None}
    ordered = [(v['score'],k) for k,v in results.items() if v['status']=='RANKED']
    ordered.sort(key=lambda pair: pair[0], reverse=True)
    last = None
    rank = 0
    for position, (score, member) in enumerate(ordered, 1):
        if score != last:
            rank, last = position, score
        results[member]['rank'] = rank
    return results
