import json
from collections import Counter

lines = open('data/training_data.jsonl', encoding='utf-8').readlines()
print(f'Total actions: {len(lines)}')

entries = []
for l in lines:
    try:
        entries.append(json.loads(l))
    except:
        pass

print(f'Valid entries: {len(entries)}')

# Count games
game_boundaries = []
for i, e in enumerate(entries):
    s = e['state']
    if s.get('setup_phase') and s['player_1']['active'] is None and s['player_2']['active'] is None:
        game_boundaries.append(i)

print(f'Total games: {len(game_boundaries)}')

# Action type distribution
actions = Counter(e['chosen_action']['type'] for e in entries)
print('\nAction types:')
for a, c in actions.most_common():
    print(f'  {a}: {c}')

# Turn distribution
turns = Counter(e['state']['turn'] for e in entries)
print('\nTurn distribution:')
for t in sorted(turns.keys())[:20]:
    print(f'  turn {t:3d}: {turns[t]} actions')

if max(turns.keys()) > 20:
    print(f'  ... up to turn {max(turns.keys())}')
