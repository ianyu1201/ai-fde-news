#!/usr/bin/env python3
"""Read local changedetection.io watches as private review leads, never news."""
import json
import os
from pathlib import Path
import urllib.request

import news


def read_watches(base, key):
    if not base.startswith(('http://127.0.0.1:', 'http://localhost:')):
        raise ValueError('只连接本机 changedetection.io')
    req = urllib.request.Request(base.rstrip('/') + '/api/v1/watch', headers={'x-api-key': key})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def leads(watches, configured, prior):
    by_url = {news.canonical_url(v.get('url', '')): v for v in watches.values()
              if isinstance(v, dict) and v.get('url')}
    result, state = [], dict(prior)
    for page in configured:
        if not page.get('enabled'):
            continue
        watch = by_url.get(news.canonical_url(page['url']))
        if not watch:
            result.append({'id': page['id'], 'status': 'watch_missing', 'url': page['url']})
            continue
        changed = watch.get('last_changed')
        if changed and state.get(page['id']) and changed != state[page['id']]:
            result.append({'id': page['id'], 'status': 'changed_unverified', 'url': page['url'],
                           'lastChanged': changed, 'note': '页面变化仅供核查；不是发布日期或已证实新闻'})
        if changed:
            state[page['id']] = changed
    return result, state


def main():
    key = os.environ.get('CHANGEDETECTION_API_KEY', '')
    if not key:
        raise SystemExit('请在本机环境变量 CHANGEDETECTION_API_KEY 设置 API key')
    base = os.environ.get('CHANGEDETECTION_BASE_URL', 'http://127.0.0.1:5000')
    prior = news.read_json(news.LOCAL / 'watch-state.json', {})
    configured = news.read_json(news.ROOT / 'watch-pages.json', [])
    found, state = leads(read_watches(base, key), configured, prior)
    news.save_json(news.LOCAL / 'watch-leads.json', {'checkedAt': news.now().isoformat(), 'items': found})
    news.save_json(news.LOCAL / 'watch-state.json', state)
    print(json.dumps({'leads': len(found), 'file': str(news.LOCAL / 'watch-leads.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
