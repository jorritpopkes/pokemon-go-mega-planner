#!/usr/bin/env python3
"""Fetch public Leek Duck-derived event data and normalize for the Mega Planner.

Uses only Python standard library. Leaves previously published JSON intact if
upstream is unreachable, invalid, or returns no usable events.
"""
import hashlib
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE = 'https://pokelitee.github.io/leak-duck/events.json'
OUT = Path('data/live-events.json')
LOCAL_TZ = ZoneInfo('Europe/Amsterdam')

# Curated, conservative lookups. If not recognized, no bonus type is guessed.
SPECIES_TYPES = {
    'abra':['Psychic'], 'kadabra':['Psychic'], 'alakazam':['Psychic'],
    'beldum':['Steel','Psychic'], 'metang':['Steel','Psychic'], 'metagross':['Steel','Psychic'],
    'mega metagross':['Steel','Psychic'], 'cresselia':['Psychic'], 'darkrai':['Dark'],
    'deoxys':['Psychic'], 'espeon':['Psychic'], 'umbreon':['Dark'],
    'mewtwo':['Psychic'], 'mewtwo x':['Psychic','Fighting'], 'mewtwo y':['Psychic'],
    'palkia':['Water','Dragon'], 'dialga':['Steel','Dragon'],
    'pawniard':['Dark','Steel'], 'bisharp':['Dark','Steel'], 'kingambit':['Dark','Steel'],
    'grookey':['Grass'], 'scorbunny':['Fire'], 'sobble':['Water'],
    'noibat':['Flying','Dragon'], 'noivern':['Flying','Dragon'],
    'clefairy':['Fairy'], 'clefable':['Fairy'], 'elgyem':['Psychic'], 'beheeyem':['Psychic'],
    'staryu':['Water'], 'starmie':['Water','Psychic'],
    'rockruff':['Rock'], 'minior':['Rock','Flying'], 'gengar':['Ghost','Poison'],
    'mega banette':['Ghost'], 'banette':['Ghost'],
    'mega beedrill':['Bug','Poison'], 'beedrill':['Bug','Poison'],
    'mega houndoom':['Dark','Fire'], 'houndoom':['Dark','Fire'],
    'mega sableye':['Dark','Ghost'], 'sableye':['Dark','Ghost'],
    'mega manectric':['Electric'], 'manectric':['Electric'],
    'mega clefable':['Fairy'],
    'kyogre':['Water'], 'groudon':['Ground'], 'rayquaza':['Dragon','Flying'],
    'eternatus':['Poison','Dragon'],
    'tornadus':['Flying'], 'espurr':['Psychic'], 'cryogonal':['Ice'],
    'falinks':['Fighting'], 'machamp':['Fighting'],
    'bounsweet':['Grass'], 'chansey':['Normal'], 'blissey':['Normal']
}


def to_local(value, is_local):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(LOCAL_TZ).strftime('%Y-%m-%dT%H:%M')
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if d.tzinfo:
            d = d.astimezone(LOCAL_TZ)
        # Naive source dates are in each player's local clock time; the
        # application displays them in local Netherlands time.
        return d.strftime('%Y-%m-%dT%H:%M')
    except ValueError:
        return None


def normalize_species(raw_name):
    name = html.unescape(str(raw_name or '')).lower().strip()
    name = re.sub(r'^(shadow|purified)\s+', '', name)
    name = re.sub(r'\s+wearing\s+.+$', '', name)
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
    if 'deoxys' in name:
        return 'deoxys'
    if 'tornadus' in name:
        return 'tornadus'
    if name.startswith('eternamax'):
        return 'eternatus'
    return name


def collect_types(item):
    info = item.get('details') if isinstance(item.get('details'), dict) else {}
    names = []
    for kind in ('spawns', 'raids'):
        for p in info.get(kind, []) or []:
            if isinstance(p, dict):
                names.append(p.get('name', ''))
    # Be conservative: title only if it clearly mentions a known species.
    title = str(item.get('title', '')).lower()
    if not names:
        for species in sorted(SPECIES_TYPES, key=len, reverse=True):
            if re.search(r'(?<![a-z])'+re.escape(species)+r'(?![a-z])', title):
                names.append(species)
    types=[]
    for name in names:
        for pokemon_type in SPECIES_TYPES.get(normalize_species(name), []):
            if pokemon_type not in types:
                types.append(pokemon_type)
    return types


def event_category(cat, title):
    cat = (cat or '').lower()
    title = title.lower()
    if 'to be announced' in title or 'tba' in title:
        return 'tba'
    if any(s in cat for s in ('raid','shadow raid')):
        return 'raid'
    return 'event'


def normalize(item):
    if not isinstance(item, dict):
        return None
    name = html.unescape(str(item.get('title', '')).strip())
    start = to_local(item.get('start_time'), item.get('is_local_time', True))
    end = to_local(item.get('end_time'), item.get('is_local_time', True))
    if not name or not start or not end or end < start:
        return None
    details = item.get('details') if isinstance(item.get('details'), dict) else {}
    bonuses = details.get('bonuses') if isinstance(details.get('bonuses'), list) else []
    bonuses = [html.unescape(str(b)) for b in bonuses if isinstance(b, str)]
    source = item.get('article_url', '')
    if not isinstance(source, str) or not source.startswith('https://'):
        source = 'https://leekduck.com/events/'
    category = event_category(item.get('category', ''), name)
    has_catches = bool(details.get('spawns') or details.get('raids')) or any(
        k in str(item.get('category', '')).lower() for k in ('community day','spotlight','raid'))
    types = collect_types(item)
    notes = 'Automatically sourced from Leek Duck via Leak Duck. '
    notes += ('Boosted types inferred from named Pokémon; confirm event details.' if types else
              'Featured types not recognized or not announced yet; check source before choosing a Mega.')
    event_id = hashlib.sha1((name+'|'+start).encode('utf-8')).hexdigest()[:14]
    return {
        'id': 'live_'+event_id,
        'name': name,
        'start': start,
        'end': end,
        'types': types,
        'bonus': '; '.join(bonuses[:3]) or html.unescape(str(item.get('description', '')).split('\n')[0])[:220] or 'See source for details',
        'category': category,
        'source': source,
        'catch': has_catches,
        'notes': notes,
    }


def generate(raw, now=None):
    if not isinstance(raw, dict):
        raise ValueError('Expected category-to-events dictionary')
    today = now or datetime.now(LOCAL_TZ)
    earliest = (today - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    latest = (today + timedelta(days=150)).strftime('%Y-%m-%dT%H:%M')
    seen = set()
    events=[]
    for arr in raw.values():
        if not isinstance(arr, list):
            continue
        for item in arr:
            ev = normalize(item)
            if not ev or ev['end'] < earliest or ev['start'] > latest or ev['id'] in seen:
                continue
            events.append(ev)
            seen.add(ev['id'])
    events.sort(key=lambda event: (event['start'],event['name']))
    if not events:
        raise ValueError('No valid events returned: refusing to overwrite last good data')
    return {'updated': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'source': SOURCE, 'events': events}


def main():
    req=urllib.request.Request(SOURCE, headers={'User-Agent': 'PokemonGoMegaPlanner/1.0 (personal event calendar)'})
    with urllib.request.urlopen(req, timeout=35) as response:
        raw=json.load(response)
    payload=generate(raw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(f"Saved {len(payload['events'])} current/upcoming events to {OUT}")


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Update failed, leaving previous data unchanged: {exc}',file=sys.stderr)
        sys.exit(1)
