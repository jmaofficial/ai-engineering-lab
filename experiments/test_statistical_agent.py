"""Live end-to-end test. Makes real Gemini/Riot calls; API must be running."""
import argparse
import json
import os
from pathlib import Path
import time

import requests
from dotenv import load_dotenv


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument('--riot-id', required=True)
    parser.add_argument('--region', default='europe')
    parser.add_argument('--url', default='http://127.0.0.1:8000/agent')
    parser.add_argument('--prompt', help='Optional user request, including desired response language')
    parser.add_argument('--require-python', action='store_true', help='Check Python execution explicitly when testing that capability')
    args = parser.parse_args()
    started = time.time()
    message = args.prompt or (
        f'Mitt Riot ID är {args.riot_id}, region {args.region}. Jag vill klättra i '
        'ranked solo/duo som mid. Gör en statistiskt underbyggd analys av vilka '
        'champions jag bör prioritera. Välj själv datamängd, filter och metod, '
        'hämta mer historik om det behövs och förklara osäkerheten.'
    )
    response = requests.post(args.url, json={'message': message}, timeout=900)
    if not response.ok:
        print('HTTP', response.status_code, response.text)
    response.raise_for_status()
    result = response.json()
    directory = Path(os.getenv('ANALYSIS_DATA_DIR', '.analysis')) / 'agent_runs'
    traces = []
    for path in directory.glob('*.json'):
        if path.stat().st_mtime >= started:
            trace = json.loads(path.read_text())
            if trace.get('answer') == result['response']:
                traces.append((path, trace))
    assert len(traces) == 1, 'No unique execution trace matches the response'
    path, trace = traces[0]
    analyses = [x for x in trace['tools'] if x['name'] == 'analyze_match_dataset']
    if args.require_python:
        assert analyses, 'The explicitly tested Python capability was not used'
        assert analyses[-1]['result'].get('success'), 'Last Python analysis was incomplete'
    if trace['tools']:
        assert trace.get('reviews') and trace['reviews'][-1]['approved'], 'Answer failed evidence review'
    print('PASS: HTTP response and execution trace; tool selection was left to the agent')
    print('Conversation:', result['conversation_id'])
    print('Trace:', path)
    print('Tools:', ', '.join(x['name'] for x in trace['tools']))
    print(result['response'])


if __name__ == '__main__':
    main()
