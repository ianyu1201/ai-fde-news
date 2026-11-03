import datetime as dt
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch
import news
import upgrade
import page_watches

SOURCE = {'id': 'test', 'name': 'Example', 'url': 'https://example.com/feed', 'kind': '官方'}


class NewsTests(unittest.TestCase):
    def test_podcast_catalog_identity_dates_and_no_audio_fetch(self):
        source = dict(SOURCE, podcastId='a' * 24, expectedTitle='示例节目', region='CN', track='interviews')
        payload = {'props': {'pageProps': {'podcast': {'pid': source['podcastId'], 'title': '示例节目',
                   'episodes': [{'eid': 'b' * 24, 'pid': source['podcastId'], 'title': 'AI与组织',
                   'shownotes': '<p>公开说明</p>', 'pubDate': self.when, 'enclosure': {'url': 'https://example.com/audio'}}]}}}}
        data = ('<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>').encode()
        item = news.parse_podcast_catalog(data, source, self.when)[0]
        self.assertEqual(item['url'], 'https://www.xiaoyuzhoufm.com/episode/' + 'b' * 24)
        self.assertEqual(item['excerpt'], '公开说明')
        self.assertEqual(item['publishedAt'], self.when)
        self.assertNotIn('enclosure', item)
        with self.assertRaisesRegex(ValueError, '主体'):
            news.parse_podcast_catalog(data, dict(source, podcastId='c' * 24), self.when)

    def test_review_batch_reserves_domestic_and_interview_slots_without_duplicates(self):
        pending = ([{'id': str(i), 'region': 'US'} for i in range(60)] +
                   [{'id': 'cn' + str(i), 'region': 'CN'} for i in range(50)] +
                   [{'id': 'podcast', 'region': 'CN', 'track': 'interviews'}])
        batch = news.review_batch(pending, 60)
        self.assertEqual(len(batch), 60)
        self.assertEqual(len({i['id'] for i in batch}), 60)
        self.assertEqual(sum(i.get('region') == 'CN' for i in batch), 41)
        self.assertIn('podcast', {i['id'] for i in batch})

    def test_explicitly_removed_interview_cannot_be_reselected(self):
        news.save_json(self.local / 'content-tracks.json', {'interviews': {'excludedEpisodes': [{'url': self.item['url']}]}})
        with patch.object(news, 'ROOT', self.local):
            with self.assertRaisesRegex(ValueError, '明确移除'):
                news.validate_reviews([self.review()], {self.item['id']: self.item})

    def test_feed_tls_keeps_certificate_verification_enabled(self):
        context = news.feed_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(len(context.get_ca_certs()), 0)

    def test_page_change_is_private_unverified_lead(self):
        url = 'https://example.com/updates'
        config = [{'id': 'updates', 'url': url, 'enabled': True}]
        watches = {'watch-id': {'url': url, 'last_changed': '2026-10-01T09:00:00Z'}}
        first, state = page_watches.leads(watches, config, {})
        self.assertEqual(first, [])
        second, state = page_watches.leads(watches, config, {'updates': '2026-09-30T09:00:00Z'})
        self.assertEqual(second[0]['status'], 'changed_unverified')
        self.assertNotIn('publishedAt', second[0])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.local = Path(self.temp.name) / 'local'
        self.dist = Path(self.temp.name) / 'dist'
        self.patches = [patch.object(news, 'LOCAL', self.local), patch.object(news, 'DIST', self.dist)]
        for p in self.patches:
            p.start()
        self.when = (news.now() - dt.timedelta(hours=2)).isoformat()
        self.item = news.make_item(SOURCE, 'A test article', 'https://example.com/a', self.when, 'agent workflow', self.when)
        self.write_scores(self.item)

    def write_scores(self, item, a=80, b=80):
        scores = news.read_json(self.local / 'scores.json', {})
        key = item['id'] + ':' + item['fingerprint'] + ':' + upgrade.SCORE_VERSION
        scores[key] = {role: {'score': value, 'contextId': 'test-context-' + role,
                            'standardVersion': upgrade.SCORE_VERSION, 'standardHash': 'a' * 64}
                       for role, value in [('A', a), ('B', b)]}
        news.save_json(self.local / 'scores.json', scores)

    def test_publication_requires_double_scores_and_exact_75_boundary(self):
        news.save_json(self.local / 'catalog.json', {self.item['id']: self.item})
        approved = news.validate_reviews([self.review()], {self.item['id']: self.item})[0]
        news.save_json(self.local / 'editorial.json', {self.item['id']: approved})
        for a, b, expected in [(74, 75, 0), (74, 76, 1), (90, 60, 1), (75, 75, 1)]:
            with self.subTest(a=a, b=b):
                self.write_scores(self.item, a, b)
                self.assertEqual(len(news.public_payload()['items']), expected)
        scores = news.read_json(self.local / 'scores.json', {})
        pair = next(iter(scores.values()))
        del pair['B']
        news.save_json(self.local / 'scores.json', scores)
        self.assertEqual(news.public_payload()['items'], [])
        news.save_json(self.local / 'scores.json', {})
        self.assertEqual(news.public_payload()['items'], [])
        self.assertTrue(news.read_json(self.local / 'editorial.json', {})[self.item['id']]['selected'])

    def test_same_context_or_different_standards_cannot_publish(self):
        news.save_json(self.local / 'catalog.json', {self.item['id']: self.item})
        approved = news.validate_reviews([self.review()], {self.item['id']: self.item})[0]
        news.save_json(self.local / 'editorial.json', {self.item['id']: approved})
        for change in [{'contextId': 'test-context-A'}, {'standardHash': 'b' * 64}, {'score': 101}]:
            self.write_scores(self.item)
            scores = news.read_json(self.local / 'scores.json', {})
            next(iter(scores.values()))['B'].update(change)
            news.save_json(self.local / 'scores.json', scores)
            self.assertEqual(news.public_payload()['items'], [])

    def test_office_uses_news_scores_but_keeps_75_publication_threshold(self):
        item = dict(self.item, track='office')
        review = self.review(item)
        review.update(themes=['协同办公'], claimType='企业自述', materialScope='官方发布公告')
        approved = news.validate_reviews([review], {item['id']: item})[0]
        news.save_json(self.local / 'catalog.json', {item['id']: item})
        news.save_json(self.local / 'editorial.json', {item['id']: approved})
        # Depth scores cannot masquerade as office news scores.
        self.assertEqual(news.public_payload()['items'], [])
        key = item['id'] + ':' + item['fingerprint'] + ':' + upgrade.OFFICE_SCORE_VERSION
        scores = {key: {role: {'score': value, 'contextId': 'office-test-' + role,
                              'standardVersion': upgrade.OFFICE_SCORE_VERSION, 'standardHash': 'a' * 64,
                              'dimensions': {'relevance': 25, 'productChange': 25, 'frontierSignal': 10, 'evidence': 10, 'increment': value - 70}}
                       for role, value in [('A', 74), ('B', 75)]}}
        news.save_json(self.local / 'scores.json', scores)
        self.assertEqual(news.public_payload()['items'], [])
        scores[key]['B'].update(score=76)
        scores[key]['B']['dimensions']['increment'] = 6
        news.save_json(self.local / 'scores.json', scores)
        self.assertEqual(news.public_payload()['items'][0]['score']['average'], 75)
        news.build()
        self.assertTrue(news.verify()['ok'])

    def test_verify_rejects_pending_or_below_threshold_public_data(self):
        news.save_json(self.local / 'catalog.json', {self.item['id']: self.item})
        approved = news.validate_reviews([self.review()], {self.item['id']: self.item})[0]
        news.save_json(self.local / 'editorial.json', {self.item['id']: approved})
        news.build()
        original = news.read_json(self.dist / 'news.json', {})
        for bad_score in [{'status': 'unscored'}, {'status': 'double', 'scores': [74, 75], 'average': 74.5}]:
            payload = json.loads(json.dumps(original))
            payload['items'][0]['score'] = bad_score
            news.save_json(self.dist / 'news.json', payload)
            with self.assertRaises(AssertionError):
                news.verify()

    def test_interview_route_keeps_exact_75_gate_and_rejects_forged_dimensions(self):
        item = dict(self.item, track='interviews')
        review = self.review(item)
        review.update(themes=['访谈'], category='访谈与洞见', claimType='受访者观点',
                      materialScope='官方文字稿中的具体片段', highlight='具体问题背景与嘉宾决策取舍')
        approved = news.validate_reviews([review], {item['id']: item})[0]
        news.save_json(self.local / 'catalog.json', {item['id']: item})
        news.save_json(self.local / 'editorial.json', {item['id']: approved})
        key = item['id'] + ':' + item['fingerprint'] + ':' + upgrade.INTERVIEW_SCORE_VERSION
        for b, expected in [(75, 0), (76, 1)]:
            scores = {key: {r: {'score': v, 'contextId': 'interview-test-' + r,
                'standardVersion': upgrade.INTERVIEW_SCORE_VERSION, 'standardHash': 'a' * 64,
                'dimensions': {'relevance': 18, 'insight': 22, 'decisionValue': 15, 'evidence': 14, 'increment': v - 69}}
                for r, v in [('A', 74), ('B', b)]}}
            news.save_json(self.local / 'scores.json', scores)
            self.assertEqual(len(news.public_payload()['items']), expected)
        news.build()
        self.assertTrue(news.verify()['ok'])
        scores[key]['B']['dimensions']['insight'] += 1
        news.save_json(self.local / 'scores.json', scores)
        self.assertEqual(news.public_payload()['items'], [])
        with self.assertRaises(AssertionError):
            news.verify()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def review(self, item=None):
        i = item or self.item
        return dict(id=i['id'], fingerprint=i['fingerprint'], selected=True, reason='相关', title='测试标题',
                    summary='测试摘要', why='业务相关', caveat='来源自述', category='业务落地', themes=['FDE'],
                    basis='primary_article', evidence=[i['url']], eventKey='same-event')

    def test_new_tracks_require_scope_and_interview_highlight(self):
        r=self.review()
        r.update(themes=['协同办公'], claimType='企业自述', materialScope='官方公告正文')
        self.assertEqual(news.validate_reviews([r], {self.item['id']: self.item})[0]['claimType'], '企业自述')
        r.update(themes=['访谈'], category='访谈与洞见', claimType='受访者观点')
        with self.assertRaises(ValueError):
            news.validate_reviews([r], {self.item['id']: self.item})
        r.update(highlight='嘉宾在具体失败案例中解释决策边界', locator='章节：失败后的选择')
        validated=news.validate_reviews([r], {self.item['id']: self.item})[0]
        self.assertEqual(validated['locator'], r['locator'])
        news.save_json(self.local / 'catalog.json', {self.item['id']:self.item})
        news.save_json(self.local / 'editorial.json', {self.item['id']:validated})
        key = self.item['id'] + ':' + self.item['fingerprint'] + ':' + upgrade.INTERVIEW_SCORE_VERSION
        news.save_json(self.local / 'scores.json', {key: {role: {
            'score': 80, 'contextId': 'interview-context-' + role,
            'standardVersion': upgrade.INTERVIEW_SCORE_VERSION, 'standardHash': 'a' * 64,
            'dimensions': {'relevance': 18, 'insight': 24, 'decisionValue': 16, 'evidence': 15, 'increment': 7}
        } for role in ('A', 'B')}})
        result=news.public_payload()['items'][0]
        self.assertEqual(result['highlight'], r['highlight'])
        news.build()
        self.assertTrue(news.verify()['ok'])
        r['claimType']='绝对真实'
        with self.assertRaises(ValueError):
            news.validate_reviews([r], {self.item['id']: self.item})

    def test_tracking_dedup_and_unsafe_url(self):
        a = news.canonical_url('https://EXAMPLE.com/a?utm_source=x&id=1#anchor')
        self.assertEqual(a, 'https://example.com/a?id=1')
        for url in ['javascript:alert(1)', 'file:///tmp/a', 'https://name:secret@example.com/a']:
            with self.assertRaises(ValueError):
                news.canonical_url(url)

    def test_rss_cdata_html_and_dtd(self):
        xml = b'<rss><channel><item><title>Test</title><link>https://example.com/a</link><pubDate>Tue, 29 Sep 2026 08:00:00 GMT</pubDate><description><![CDATA[<!DOCTYPE html><p>agent <b>workflow</b></p><script>bad()</script>]]></description></item></channel></rss>'
        item = news.parse_feed(xml, SOURCE, self.when)[0]
        self.assertEqual(item['excerpt'], 'agent workflow')
        self.assertEqual(item['publishedAt'], '2026-09-29T16:00:00+08:00')
        with self.assertRaises(ValueError):
            news.parse_feed(b'<!DOCTYPE rss [<!ENTITY x "secret">]><rss><channel/></rss>', SOURCE, self.when)

    def test_atom_relative_url(self):
        data = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom</title><link rel="alternate" href="/article"/><published>2026-09-29T10:00:00Z</published><summary>&lt;p&gt;Hi&lt;/p&gt;</summary></entry></feed>'
        item = news.parse_feed(data, SOURCE, self.when)[0]
        self.assertEqual(item['url'], 'https://example.com/article')
        self.assertEqual(item['excerpt'], 'Hi')

    def test_invalid_feed(self):
        with self.assertRaises(ValueError):
            news.parse_feed(b'<html><body>Not RSS</body></html>', SOURCE, self.when)

    def test_missing_future_and_naive_dates_rejected(self):
        for date in [None, '2026-09-30', (news.now() + dt.timedelta(days=1)).isoformat()]:
            i = dict(self.item, publishedAt=date)
            with self.assertRaises(ValueError):
                news.validate_reviews([self.review(i)], {i['id']: i})

    def test_stale_or_duplicate_review_rejected(self):
        r = self.review()
        with self.assertRaises(ValueError):
            news.validate_reviews([dict(r, fingerprint='old')], {self.item['id']: self.item})
        with self.assertRaises(ValueError):
            news.validate_reviews([r, r], {self.item['id']: self.item})

    def test_rejected_review_stays_out(self):
        i = self.item
        r = {'id': i['id'], 'fingerprint': i['fingerprint'], 'selected': False, 'reason': '无关'}
        result = news.validate_reviews([r], {i['id']: i})[0]
        self.assertEqual(news.pending_items({i['id']: i}, {i['id']: result}), [])
        changed = dict(i, fingerprint='new')
        self.assertEqual(len(news.pending_items({i['id']: changed}, {i['id']: result})), 1)

    def test_atomic_review_no_partial_write(self):
        news.save_json(self.local / 'catalog.json', {self.item['id']: self.item})
        path = self.local / 'reviews.json'
        news.save_json(path, [self.review(), {'id': 'unknown'}])
        with self.assertRaises(ValueError):
            news.apply_reviews(path)
        self.assertFalse((self.local / 'editorial.json').exists())

    def test_event_merge_and_changed_source_gate(self):
        i1 = self.item
        i2 = news.make_item(SOURCE, 'Another', 'https://example.com/b', self.when, 'another excerpt', self.when)
        self.write_scores(i2)
        catalog = {i['id']: i for i in [i1, i2]}
        reviews = news.validate_reviews([self.review(i1), self.review(i2)], catalog)
        news.save_json(self.local / 'catalog.json', catalog)
        news.save_json(self.local / 'editorial.json', {r['id']: r for r in reviews})
        self.assertEqual(len(news.public_payload()['items']), 1)
        self.assertEqual(len(news.public_payload()['items'][0]['evidence']), 2)
        catalog[i1['id']]['fingerprint'] = 'changed'
        catalog[i2['id']]['fingerprint'] = 'changed'
        news.save_json(self.local / 'catalog.json', catalog)
        self.assertEqual(news.public_payload()['items'], [])

    def test_html_injection_and_export_privacy(self):
        i = self.item
        r = self.review()
        r['summary'] = '</script><script>alert(1)</script>'
        approved = news.validate_reviews([r], {i['id']: i})
        news.save_json(self.local / 'catalog.json', {i['id']: i})
        news.save_json(self.local / 'editorial.json', {r['id']: approved[0]})
        news.build()
        page = (self.dist / 'index.html').read_text()
        self.assertNotIn('</script><script>alert(1)</script>', page)
        self.assertNotIn('agent workflow', page)
        self.assertTrue(news.verify()['ok'])

    def test_failed_source_preserves_prior_catalog(self):
        news.save_json(self.local / 'catalog.json', {self.item['id']: self.item})
        with patch.object(news, 'fetch_source', side_effect=lambda s, t: ([], dict(s, status='error', checkedAt=t, error='offline'))):
            with self.assertRaisesRegex(ValueError, '所有 RSS 信源采集失败'):
                news.collect()
        self.assertIn(self.item['id'], news.read_json(self.local / 'catalog.json', {}))
        self.assertTrue(all(s['status'] == 'error' for s in news.read_json(self.local / 'collection.json', {})['sources']))


if __name__ == '__main__':
    unittest.main()
