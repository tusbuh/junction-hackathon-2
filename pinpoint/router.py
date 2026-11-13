"""Language-agnostic fallback router: when the primary rules don't route a question, map it to a canonical
English template with the multilingual lexicon (0 LLM calls). Optional last resort: a small LLM that only
returns the canonical template (never the answer), used only if ANTHROPIC_API_KEY is set."""
import os, re, json
from .lexicon import has, first, norm

QUOTE_RX = re.compile(r"[«“„\"']\s*([^»”“\"']+?)\s*[»”“\"']")


def quoted(q):
    return QUOTE_RX.findall(q)


def strip_quotes(q):
    return QUOTE_RX.sub(' ', q)


def canonical_swiss(q):
    bare = strip_quotes(q)
    qs = quoted(q)
    area = has('area', bare)
    m = re.search(r'(?:^|\s)([A-Z])(?=[\s,.?)]|$)', strip_quotes(q))
    if area and has('apartment', bare) and m:
        return f"What is the net floor area of apartment {m.group(1)} in m², summing all its rooms except balconies?"
    if qs and has('labelled', bare):
        return f"What is the total area in m² of all rooms labelled '{qs[0]}'?" if area else f"How many rooms labelled '{qs[0]}' are there?"
    if area:
        return "What is the total net floor area in m² of all numbered indoor rooms?"
    c = first(bare, ['apartment', 'door', 'window', 'basin', 'toilet', 'bathtub', 'shower'])
    return {'apartment': 'How many apartments are shown?', 'door': 'How many doors are drawn?', 'window': 'How many windows are drawn?',
            'basin': 'How many washbasins are drawn?', 'toilet': 'How many toilets are drawn?', 'bathtub': 'How many bathtubs are drawn?',
            'shower': 'How many showers are drawn?'}.get(c)


def canonical_ifc(q, storeys=()):
    bare = strip_quotes(q)
    qs = quoted(q)
    st = next((x for x in qs if x in storeys), None)
    on = f" on the floor plan of '{st}'" if st else ''
    room = next((x for x in qs if re.search(r'\([^()]+\)$', x)), None)
    if room and has('area', bare):
        return f"What is the net floor area of the room '{room}'" + (f" on '{st}'" if st else '') + ", in m²?"
    c = first(bare, ['sanitary', 'door', 'window', 'room', 'wall', 'column', 'beam', 'stair', 'slab'])
    if c is None:
        return None
    noun = {'sanitary': 'sanitary fixtures', 'door': 'doors', 'window': 'windows', 'room': 'rooms (spaces)', 'wall': 'walls',
            'column': 'columns', 'beam': 'beams', 'stair': 'stairs', 'slab': 'slabs'}[c]
    if has('side_area', bare): return f"What is the total net side area of all {noun}{on}, in m²?"
    if has('volume', bare): return f"What is the total net volume of all {noun}{on}, in m³?"
    if has('length', bare) and c in ('wall', 'beam'): return f"What is the total length of all {noun}{on}, in metres?"
    if has('area', bare) and c == 'room': return f"What is the total net floor area of all rooms{on}, in m²?"
    return f"How many {noun} are there{on}?"


def llm_canonical(q, kind):
    """Optional: ask a small model for the canonical template only. Returns (text, eur) or (None, 0)."""
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        return None, 0.0
    try:
        import urllib.request
        prompt = (f"Rewrite this question about a {kind} as ONE short English question using these words exactly where they apply: "
                  "doors, windows, toilets, washbasins, bathtubs, showers, apartments, rooms labelled '<name>', net floor area of apartment <X>, "
                  "walls, slabs, beams, columns, stairs, sanitary fixtures, total net volume, total length, net side area, on the floor plan of '<storey>'. "
                  "Keep quoted names verbatim. Output only the question.\n\nQuestion: " + q)
        body = json.dumps({'model': os.environ.get('PINPOINT_ROUTER_MODEL', 'claude-haiku-5-5'), 'max_tokens': 80,
                           'messages': [{'role': 'user', 'content': prompt}]}).encode()
        req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=body, headers={
            'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
        r = json.loads(urllib.request.urlopen(req, timeout=20).read())
        u = r.get('usage', {})
        eur = (u.get('input_tokens', 0) * 1.0 + u.get('output_tokens', 0) * 5.0) / 1e6 * 0.93   # Haiku-class $/Mtok -> €
        return r['content'][0]['text'].strip(), eur
    except Exception:
        return None, 0.0
