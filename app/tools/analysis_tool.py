"""Local datasets and container-isolated, agent-written statistical analysis."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from threading import Thread
import uuid

from app.settings import positive_int
from app.tools.riot_tool import RiotError


WRAPPER = '''
import json, sys
import pandas as pd
import numpy as np
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.proportion import proportion_confint
def proportion_ci(wins, n, confidence=0.95, method='wilson'):
    if n <= 0 or not 0 <= wins <= n:
        raise ValueError('Require 0 <= wins <= n and n > 0')
    return tuple(float(x) for x in proportion_confint(wins, n, alpha=1-confidence, method=method))
with open('/data/dataset.json') as f:
    dataset = json.load(f)
matches = dataset['matches']
rows = []
for match in matches:
    info = match.get('info', {})
    participants = info.get('participants', [])
    player = next((p for p in participants if p.get('puuid') == dataset['puuid']), None)
    if player is None:
        continue
    row = dict(player)
    row.update(match_id=match['metadata']['matchId'], queueId=info.get('queueId'),
               gameDuration=info.get('gameDuration'), gameStartTimestamp=info.get('gameStartTimestamp'),
               patch='.'.join(info.get('gameVersion', '').split('.')[:2]))
    opponent = next((p for p in participants if p.get('teamId') != player.get('teamId')
                     and p.get('teamPosition') == player.get('teamPosition')
                     and player.get('teamPosition')), {})
    row['opponentChampion'] = opponent.get('championName')
    rows.append(row)
df = pd.json_normalize(rows)
_input_ids = set(df.get('match_id', []))
def _frame_profile(frame):
    profile = {'rows': len(frame), 'unique_matches': int(frame['match_id'].nunique())}
    for column in ('teamPosition', 'patch', 'queueId', 'gameEndedInEarlySurrender'):
        if column in frame.columns:
            profile[column] = {str(k): int(v) for k, v in frame[column].value_counts(dropna=False).items()}
    return profile
_input_profile = _frame_profile(df) if 'match_id' in df.columns else {'rows': 0}
exec(compile(sys.stdin.read(), '<agent-analysis>', 'exec'))
_profiles = {}
for _name, _frame in list(globals().items()):
    if isinstance(_frame, pd.DataFrame) and 'match_id' in _frame.columns:
        if set(_frame['match_id'].dropna()).issubset(_input_ids):
            _profiles[_name] = _frame_profile(_frame)
print('\\n__ANALYSIS_METADATA__' + json.dumps({'input_profile': _input_profile, 'frame_profiles': _profiles}))
'''


class AnalysisTools:
    def __init__(self, riot, root=None):
        self.riot = riot
        self.root = Path(root or os.getenv('ANALYSIS_DATA_DIR', '.analysis')).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / 'matches.sqlite'
        self.max_matches = positive_int('ANALYSIS_MAX_MATCHES', 1000)
        self.timeout = positive_int('ANALYSIS_TIMEOUT_SECONDS', 30)
        self.output_limit = positive_int('ANALYSIS_OUTPUT_CHARS', 12000)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, puuid TEXT, region TEXT, queue INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS matches (dataset TEXT, id TEXT, payload TEXT, PRIMARY KEY(dataset,id))')
            db.execute('CREATE TABLE IF NOT EXISTS pages (dataset TEXT, start INTEGER, end INTEGER, exhausted INTEGER)')

    def _db(self):
        return sqlite3.connect(self.database)

    def collect_more_matches(self, dataset_id: str, count: int = 20) -> dict:
        """Continue collecting history using a short dataset ID, without copying PUUIDs.

        Choose page size yourself; call again while older history is useful.
        Automatically resumes the first contiguous uncollected offset. Only
        history_exhausted=true means Riot returned no more history. An error is
        NOT history exhaustion. Correct errors or report collection incomplete.
        """
        profile = self.inspect_match_dataset(dataset_id)
        if 'error' in profile:
            return profile
        if profile['history_exhausted']:
            return {'dataset_id': dataset_id, 'history_exhausted': True,
                    'stored_matches': profile['stored_matches'], 'added': 0,
                    'next_start': profile['next_start'], 'error': None}
        return self.collect_match_dataset(profile['puuid'], profile['region'], count,
                                          profile['next_start'], profile['queue'])

    def inspect_match_dataset(self, dataset_id: str) -> dict:
        """Inspect stored data BEFORE choosing filters, sample size and statistical methods.

        Returns full column names, roles, patches, remake flags, dates, missing
        player count and fetched history ranges. No filters are applied. Use
        next_start to continue contiguous history collection. No fixed sample
        count implies statistical sufficiency. Missing remake flags are unknown.
        """
        from collections import Counter
        if not re.fullmatch(r'[a-f0-9]{24}', dataset_id):
            return {'error': 'Invalid dataset ID'}
        with self._db() as db:
            account = db.execute('SELECT puuid,region,queue FROM datasets WHERE id=?', (dataset_id,)).fetchone()
            if not account:
                return {'error': 'Unknown dataset'}
            payloads = [json.loads(row[0]) for row in db.execute('SELECT payload FROM matches WHERE dataset=?', (dataset_id,))]
            ranges = db.execute('SELECT start,end,exhausted FROM pages WHERE dataset=? ORDER BY start', (dataset_id,)).fetchall()
        cursor = 0
        exhausted = False
        for start, end, empty in ranges:
            if start <= cursor:
                cursor = max(cursor, end)
                exhausted = exhausted or bool(empty)
        rows, missing, columns, timestamps = [], 0, set(), []
        for match in payloads:
            info = match.get('info', {})
            player = next((p for p in info.get('participants', []) if p.get('puuid') == account[0]), None)
            if player is None:
                missing += 1
                continue
            rows.append((player, info))
            columns.update(player)
            if info.get('gameStartTimestamp'):
                timestamps.append(info['gameStartTimestamp'])
        columns.update(['match_id', 'patch', 'queueId', 'gameDuration', 'gameStartTimestamp', 'opponentChampion'])
        return {'dataset_id': dataset_id, 'puuid': account[0], 'region': account[1], 'queue': account[2],
                'stored_matches': len(payloads), 'missing_player': missing,
                'roles': dict(Counter(p.get('teamPosition') or 'UNKNOWN' for p, _ in rows)),
                'patches': dict(Counter('.'.join(i.get('gameVersion', '').split('.')[:2]) for _, i in rows)),
                'remake_flags': dict(Counter(str(p.get('gameEndedInEarlySurrender', 'UNKNOWN')) for p, _ in rows)),
                'date_range_ms': [min(timestamps), max(timestamps)] if timestamps else [],
                'columns': sorted(columns), 'next_start': cursor,
                'history_exhausted': exhausted, 'fetched_ranges': ranges,
                'requests_remaining_this_turn': self.riot.remaining,
                'max_page_size': self.riot.max_matches,
                'note': 'Older datasets without recorded page ranges may start at 0; cached matches are deduplicated. Raw nested participant fields are flattened with dots in df.'}

    def collect_match_dataset(self, puuid: str, region: str = 'europe', count: int = 20,
                              start: int = 0, queue: int = 420) -> dict:
        """Collect a page of RAW matches into persistent local storage; no role/patch filtering.

        Choose count and start yourself, fetch more pages as needed. queue=0 means
        all queues, 420 solo/duo, 440 flex. Returns dataset_id, cursor, coverage and
        errors, not raw data. Analyze with analyze_match_dataset. Resource caps are
        not statistical stopping criteria. An empty page confirms history exhaustion.
        """
        if queue not in (0, 420, 440) or not 1 <= count <= min(100, self.riot.max_matches) or not 0 <= start <= 10000:
            return {'error': f'queue must be 0/420/440, count 1..{min(100, self.riot.max_matches)}, start 0..10000'}
        dataset_id = hashlib.sha256(f'{puuid}:{region}:{queue}'.encode()).hexdigest()[:24]
        with self._db() as db:
            db.execute('INSERT OR IGNORE INTO datasets VALUES (?,?,?,?)', (dataset_id, puuid, region, queue))
            params = {'start': start, 'count': count}
            if queue:
                params['queue'] = queue
            from urllib.parse import quote
            try:
                ids = self.riot._get(region, f'/lol/match/v5/matches/by-puuid/{quote(puuid, safe="")}/ids', params)
            except RiotError as error:
                return {'dataset_id': dataset_id, 'error': str(error), 'next_start': start,
                        'history_exhausted': False, 'collection_status': 'blocked',
                        'next_action': 'Collection failed, NOT end of history. For an existing dataset use collect_more_matches to avoid copying PUUIDs.'}
            consumed, added, error = 0, 0, None
            for match_id in ids:
                if db.execute('SELECT 1 FROM matches WHERE dataset=? AND id=?', (dataset_id, match_id)).fetchone():
                    consumed += 1
                    continue
                total = db.execute('SELECT count(*) FROM matches WHERE dataset=?', (dataset_id,)).fetchone()[0]
                if total >= self.max_matches:
                    error = 'Dataset resource cap reached; not evidence of statistical sufficiency.'
                    break
                try:
                    match = self.riot._get(region, f'/lol/match/v5/matches/{quote(match_id, safe="")}')
                except RiotError as exc:
                    error = str(exc)
                    break
                db.execute('INSERT INTO matches VALUES (?,?,?)', (dataset_id, match_id, json.dumps(match)))
                added += 1
                consumed += 1
            total = db.execute('SELECT count(*) FROM matches WHERE dataset=?', (dataset_id,)).fetchone()[0]
            db.execute('INSERT INTO pages VALUES (?,?,?,?)', (dataset_id, start, start + consumed, int(not ids)))
        return {'dataset_id': dataset_id, 'stored_matches': total, 'added': added,
                'next_start': start + consumed, 'history_exhausted': not ids,
                'page_full': len(ids) == count, 'error': error,
                'requests_remaining_this_turn': self.riot.remaining,
                'max_page_size': self.riot.max_matches,
                'collection_status': 'blocked' if error else ('history_exhausted' if not ids else 'page_collected'),
                'note': 'History offsets can shift when new games are played; duplicates are deduplicated. No filters applied.'}

    def analyze_match_dataset(self, dataset_id: str, code: str, rationale: str) -> dict:
        """Execute Python analysis in an isolated networkless container.

        Explain analysis plan, filters and stopping criteria in rationale BEFORE
        testing. Available: df (unfiltered player rows), matches (raw match dicts),
        pd, np, stats (scipy), sm (statsmodels). Inspect df.columns/dtypes first.
        Print df.columns.tolist() for ALL names; pandas Index display truncates.
        Standard names: match_id (not gameId), championName, teamPosition, win,
        kills, deaths, assists, totalDamageDealtToChampions, totalMinionsKilled,
        neutralMinionsKilled, gameDuration (seconds), patch, queueId,
        gameStartTimestamp, opponentChampion. Check optional fields before use.
        Inspect gameEndedInEarlySurrender and justify remake inclusion/exclusion.
        proportion_ci(wins,n,confidence=0.95,method='wilson') is available; choose
        method as appropriate (statsmodels methods, e.g. wilson or beta).
        Alternatively stats.binomtest(wins,n).proportion_ci() is valid.
        stats.binom.interval describes a distribution of counts for GIVEN p,
        NOT a confidence interval estimating unknown win probability.
        Choose sample size, filters and tests based on the question and uncertainty.
        Print compact results including sample sizes, exclusions, intervals and
        limitations. Use fixed random seeds. Do not repeatedly test until significant;
        distinguish exploratory findings from confirmatory tests. No API keys/network.
        """
        if not re.fullmatch(r'[a-f0-9]{24}', dataset_id) or not rationale.strip() or len(code) > 30000:
            return {'error': 'Invalid dataset ID, empty rationale, or code exceeds 30000 characters.'}
        with self._db() as db:
            dataset = db.execute('SELECT puuid FROM datasets WHERE id=?', (dataset_id,)).fetchone()
            if not dataset:
                return {'error': 'Unknown dataset. Collect matches first.'}
            matches = [json.loads(row[0]) for row in db.execute('SELECT payload FROM matches WHERE dataset=? ORDER BY id', (dataset_id,))]
        run_id = uuid.uuid4().hex
        name = 'lol-analysis-' + run_id
        with tempfile.TemporaryDirectory(prefix='lol-analysis-') as directory:
            path = Path(directory) / 'dataset.json'
            path.write_text(json.dumps({'puuid': dataset[0], 'matches': matches}))
            os.chmod(directory, 0o755)
            os.chmod(path, 0o444)
            command = ['docker', 'run', '--rm', '--pull=never', '--log-driver=none', '--name', name,
                       '--network=none', '--read-only', '--cap-drop=ALL',
                       '--security-opt=no-new-privileges', '--user=65534:65534',
                       '--memory=512m', '--cpus=1', '--pids-limit=64',
                       '--tmpfs=/tmp:rw,noexec,nosuid,size=32m',
                       '--ulimit=nofile=128:128', '--mount', f'type=bind,src={path},dst=/data/dataset.json,readonly',
                       '-e', 'OPENBLAS_NUM_THREADS=1', '-e', 'MPLCONFIGDIR=/tmp/matplotlib',
                       '-i', 'lol-analysis:local', 'python', '-c', WRAPPER]
            output = bytearray()
            truncated = False
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                def read_output():
                    nonlocal truncated
                    while chunk := process.stdout.read(1024):
                        available = self.output_limit - len(output)
                        output.extend(chunk[:max(0, available)])
                        if len(chunk) > available:
                            truncated = True
                            process.kill()
                            break
                reader = Thread(target=read_output, daemon=True)
                reader.start()
                try:
                    process.stdin.write(code.encode())
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                timed_out = False
                try:
                    process.wait(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.kill()
                    process.wait()
                reader.join(timeout=2)
                if not reader.is_alive():
                    process.stdout.close()
                result = {'success': process.returncode == 0 and not truncated and not timed_out,
                          'exit_code': process.returncode, 'output': output.decode(errors='replace'),
                          'truncated': truncated, 'timed_out': timed_out}
                if not result['success']:
                    result['next_action'] = 'Analysis incomplete. Fix code using inspect_match_dataset column names, or reduce output/runtime, then rerun. Do not claim failed computations succeeded.'
                else:
                    text, marker, metadata = result['output'].rpartition('__ANALYSIS_METADATA__')
                    if marker:
                        try:
                            result.update(json.loads(metadata))
                            result['output'] = text.rstrip()
                        except ValueError:
                            result['success'] = False
                            result['error'] = 'Analysis metadata could not be parsed.'
                    else:
                        result['success'] = False
                        result['error'] = 'Analysis ended before execution metadata was produced.'
            except OSError:
                result = {'error': 'Docker unavailable. Build the analysis image and start Docker; no host execution fallback.'}
            finally:
                try:
                    subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        # Keep reproducible code, intent and output outside model context.
        audit = self.root / 'runs'
        audit.mkdir(exist_ok=True)
        (audit / f'{run_id}.json').write_text(json.dumps({'dataset_id': dataset_id,
            'rationale': rationale, 'code': code, 'result': result}, ensure_ascii=False))
        return {'run_id': run_id, **result}
