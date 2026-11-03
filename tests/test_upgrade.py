import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import upgrade
import news


class UpgradeTests(unittest.TestCase):
    def test_interview_route_does_not_reuse_depth_and_requires_valid_dimensions(self):
        item = dict(self.item, track='interviews')
        catalog = {item['id']: item}
        old_key = item['id'] + ':' + item['fingerprint'] + ':' + upgrade.SCORE_VERSION
        old = {old_key: {r: {'score': 90, 'contextId': 'old-' + r + '-context',
                             'standardVersion': upgrade.SCORE_VERSION, 'standardHash': 'a' * 64} for r in ('A', 'B')}}
        upgrade.save(self.local / 'scores.json', old)
        self.assertEqual(upgrade.score_view(item, old)['status'], 'unscored')
        self.assertEqual(upgrade.score_materials(catalog, {}, old, 'A')['items'], [])
        batch = upgrade.score_materials(catalog, {}, old, 'A', track='interviews')
        self.assertEqual(batch['standardVersion'], upgrade.INTERVIEW_SCORE_VERSION)
        self.assertNotEqual(batch['standardHash'], upgrade.score_digest())
        receipt = dict(batch, contextId='interview-A-context', model='test-fixture')
        receipt['items'] = [{'id': item['id'], 'fingerprint': item['fingerprint'], 'score': 80,
                            'reason': '仅据具体片段评价嘉宾观点、决策取舍及材料边界。',
                            'dimensions': {'relevance': 18, 'insight': 24, 'decisionValue': 16, 'evidence': 15, 'increment': 7}}]
        path = self.local / 'interview.json'
        for bad in ({}, {'relevance': True, 'insight': 24, 'decisionValue': 16, 'evidence': 15, 'increment': 7},
                    {'relevance': 21, 'insight': 21, 'decisionValue': 16, 'evidence': 15, 'increment': 7}):
            valid = receipt['items'][0]['dimensions']
            receipt['items'][0]['dimensions'] = bad
            upgrade.save(path, receipt)
            with self.assertRaisesRegex(ValueError, '五项'):
                upgrade.import_scores(path, catalog)
            receipt['items'][0]['dimensions'] = valid
        upgrade.save(path, receipt)
        upgrade.import_scores(path, catalog)
        receipt.update(reviewer='B', contextId='interview-B-context')
        upgrade.save(path, receipt)
        upgrade.import_scores(path, catalog)
        saved = upgrade.load(self.local / 'scores.json', {})
        self.assertEqual(saved[old_key], old[old_key])
        self.assertEqual(upgrade.score_view(item, saved)['profileLabel'], '访谈与片段洞见')

    def test_legacy_interview_requires_frozen_receipts_and_never_overrides_new_scores(self):
        import hashlib
        item = dict(self.item, track='interviews')
        key = item['id'] + ':' + item['fingerprint'] + ':' + upgrade.SCORE_VERSION
        pair = {r: {'score': 80, 'contextId': 'legacy-' + r + '-context',
                    'standardVersion': upgrade.SCORE_VERSION, 'standardHash': 'a' * 64} for r in ('A', 'B')}
        scores = {key: pair}
        digest = hashlib.sha256(json.dumps(pair, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        upgrade.save(self.local / 'interview-legacy-scores.json', {'receipts': {key: digest}})
        self.assertTrue(upgrade.score_view(item, scores)['legacyInterview'])
        pair['A']['score'] = 81
        self.assertEqual(upgrade.score_view(item, scores)['status'], 'unscored')
        pair['A']['score'] = 80
        scores[item['id'] + ':' + item['fingerprint'] + ':' + upgrade.INTERVIEW_SCORE_VERSION] = {}
        self.assertEqual(upgrade.score_view(item, scores)['status'], 'unscored')

    def test_office_route_uses_separate_standard_and_does_not_reuse_depth_scores(self):
        item = dict(self.item, track='office')
        catalog = {item['id']: item}
        editorial = {item['id']: {'selected': True, 'themes': ['协同办公']}}
        old_key = item['id'] + ':' + item['fingerprint'] + ':' + upgrade.SCORE_VERSION
        old = {old_key: {role: {'score': 95, 'contextId': 'old-context-' + role,
                              'standardVersion': upgrade.SCORE_VERSION, 'standardHash': 'a' * 64}
                        for role in ['A', 'B']}}
        self.assertEqual(upgrade.score_view(item, old, editorial[item['id']])['status'], 'unscored')
        self.assertEqual(upgrade.score_materials(catalog, editorial, old, 'A')['items'], [])
        batch = upgrade.score_materials(catalog, editorial, old, 'A', track='office')
        self.assertEqual(len(batch['items']), 1)
        self.assertEqual(batch['standardVersion'], upgrade.OFFICE_SCORE_VERSION)
        self.assertNotEqual(batch['standardHash'], upgrade.score_digest())

    def test_office_import_requires_dimension_sum_and_preserves_old_receipts(self):
        item = dict(self.item, track='office')
        catalog = {item['id']: item}
        old_key = item['id'] + ':' + item['fingerprint'] + ':' + upgrade.SCORE_VERSION
        upgrade.save(self.local / 'scores.json', {old_key: {'A': {'score': 65}}})
        batch = upgrade.score_materials(catalog, {}, {}, 'A', track='office')
        receipt = dict(batch, contextId='office-context-A', model='test-fixture')
        receipt['items'] = [{'id': item['id'], 'fingerprint': item['fingerprint'], 'score': 80,
                              'reason': '仅据测试提供的材料评价具体工作流变化与发布阶段。',
                              'dimensions': {'relevance': 20, 'productChange': 20, 'frontierSignal': 16, 'evidence': 16, 'increment': 8}}]
        path = self.local / 'office.json'
        upgrade.save(path, receipt)
        upgrade.import_scores(path, catalog)
        receipt['reviewer'] = 'B'
        receipt['contextId'] = 'office-context-B'
        receipt['items'][0]['dimensions']['productChange'] = 21
        upgrade.save(path, receipt)
        with self.assertRaisesRegex(ValueError, '五项'):
            upgrade.import_scores(path, catalog)
        receipt['items'][0]['score'] = 81
        upgrade.save(path, receipt)
        upgrade.import_scores(path, catalog)
        scores = upgrade.load(self.local / 'scores.json', {})
        self.assertEqual(scores[old_key]['A']['score'], 65)
        self.assertEqual(upgrade.score_view(item, scores)['average'], 80.5)
        self.assertEqual(upgrade.score_view(item, scores)['profileLabel'], '产品与行业动态')
        depth = dict(item, track='depth')
        with self.assertRaisesRegex(ValueError, '路线'):
            upgrade.import_scores(path, {item['id']: depth})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.local = Path(self.temp.name)
        self.patch = patch.object(upgrade, 'LOCAL', self.local)
        self.patch.start()
        self.now = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)
        self.article_id = 'a' * 20
        self.item = {
            'id': self.article_id,
            'fingerprint': 'fingerprint-v1',
            'originalTitle': 'AI Native FDE production workflow',
            'excerpt': 'A reported customer deployment with engineering details.',
            'sourceKind': '一手来源',
            'source': 'Example',
            'sourceId': 'example',
            'publisherId': 'example-publisher',
            'publishedAt': (self.now - dt.timedelta(hours=2)).isoformat(),
            'url': 'https://example.com/story',
        }
        self.catalog = {self.article_id: self.item}

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_user_readings_keep_approval_separate_from_news_scores(self):
        entry = {'id': 'book-smart', 'title': '智能', 'source': '作者',
                 'summary': '用户已经认可的阅读材料。', 'kind': '书籍',
                 'dateLabel': '出版日期待核实', 'url': 'https://example.com/book',
                 'themes': ['AI Native'], 'approvedBy': 'user',
                 'privateFile': '/private/local-book', 'score': 100}
        path = self.local / 'recommended-readings.json'
        path.write_text(json.dumps([entry]))
        with patch.object(news, 'ROOT', self.local):
            result = news.recommended_readings()[0]
            self.assertEqual(result['approvedBy'], 'user')
            self.assertNotIn('score', result)
            self.assertNotIn('publishedAt', result)
            self.assertNotIn('privateFile', result)
            entry['url'] = 'javascript:alert(1)'
            path.write_text(json.dumps([entry]))
            with self.assertRaises(ValueError):
                news.recommended_readings()

    def test_deep_preference_recall_without_topic_keywords(self):
        item = dict(self.item, originalTitle='Organizational operating model', excerpt='A systematic transformation report')
        self.assertGreater(upgrade.preference_hint(item), 0)
        batch = upgrade.score_materials({item['id']: item}, {}, {}, 'A')
        self.assertEqual(len(batch['items']), 1)
        self.assertIn('positiveExamples', batch['readerProfile'])

    def test_future_editorial_reading_requires_evidence(self):
        entry = {'id': 'future-handbook', 'title': '组织实践报告', 'source': '作者',
                 'summary': '经过核查的新深度阅读材料。', 'kind': '报告', 'dateLabel': '2026年8月',
                 'url': 'https://example.com/report', 'themes': ['AI Native'],
                 'approvedBy': 'editorial', 'reason': '组织方法与偏好契合', 'basis': 'primary_article'}
        path = self.local / 'recommended-readings.json'
        with patch.object(news, 'ROOT', self.local):
            path.write_text(json.dumps([entry]))
            with self.assertRaises(ValueError):
                news.recommended_readings()
            entry['evidence'] = ['https://example.com/report']
            path.write_text(json.dumps([entry]))
            self.assertEqual(news.recommended_readings()[0]['approvedBy'], 'editorial')

    def test_score_batches_skip_only_completed_reviewer_and_import_as_pair(self):
        key = self.article_id + ':fingerprint-v1:' + upgrade.SCORE_VERSION
        empty = upgrade.score_materials(self.catalog, {}, {}, 'A')
        self.assertEqual([x['id'] for x in empty['items']], [self.article_id])
        self.assertLessEqual(len(empty['items'][0]['excerpt']), 900)

        scores = {key: {'A': {'score': 84, 'contextId': 'review-context-A'}}}
        self.assertEqual(upgrade.score_materials(self.catalog, {}, scores, 'A')['items'], [])
        self.assertEqual(len(upgrade.score_materials(self.catalog, {}, scores, 'B')['items']), 1)

        def import_batch(reviewer, context):
            path = self.local / f'{reviewer}.json'
            path.write_text(json.dumps({
                'standardVersion': upgrade.SCORE_VERSION,
                'standardHash': upgrade.score_digest(),
                'reviewer': reviewer,
                'contextId': context,
                'model': 'test-model',
                'items': [{'id': self.article_id, 'fingerprint': 'fingerprint-v1',
                           'score': 78 if reviewer == 'A' else 79, 'reason': '材料给出了实际部署方式与可迁移工程信息。'}],
            }), encoding='utf-8')
            return upgrade.import_scores(path, self.catalog)

        import_batch('A', 'review-context-A')
        with self.assertRaises(ValueError):
            import_batch('B', 'review-context-A')
        import_batch('B', 'review-context-B')
        self.assertEqual(upgrade.score_view(self.item, upgrade.load(self.local / 'scores.json', {}))['status'], 'double')
        self.assertEqual(upgrade.score_view(self.item, upgrade.load(self.local / 'scores.json', {}))['average'], 78.5)

    def test_vector_relation_merge_keeps_unrelated_reports_separate(self):
        a = {'id': self.article_id, 'eventKey': 'event-a', 'fingerprint': 'fa'}
        b = {'id': 'b' * 20, 'eventKey': 'event-b', 'fingerprint': 'fb'}
        c = {'id': 'c' * 20, 'eventKey': 'event-c', 'fingerprint': 'fc'}
        merged = upgrade.group_rows([a, b, c], {
            'pair': {'a': a['id'], 'b': b['id'], 'relation': 'SAME_STORY',
                     'fingerprintA': 'fa', 'fingerprintB': 'fb'},
            'unrelated': {'a': a['id'], 'b': c['id'], 'relation': 'UNRELATED',
                          'fingerprintA': 'fa', 'fingerprintB': 'fc'},
        })
        self.assertEqual(sorted(map(len, merged)), [1, 2])

    def test_candidate_recall_skips_known_pairs_and_old_reports(self):
        now = dt.datetime.now(dt.timezone.utc)
        ids = ['a' * 20, 'b' * 20, 'c' * 20, 'd' * 20]
        catalog = {}
        editorial = {}
        for i, article_id in enumerate(ids):
            catalog[article_id] = {
                'id': article_id, 'fingerprint': f'fp-{i}',
                'originalTitle': f'AI Native agent deployment report {i}',
                'excerpt': 'Customer workflow implementation and production evidence.',
                'publishedAt': (now - dt.timedelta(days=20 if i == 3 else 1)).isoformat(),
            }
            editorial[article_id] = {'selected': True, 'fingerprint': f'fp-{i}', 'eventKey': f'event-{i}'}
        relations = {'a:b': {'a': ids[0], 'b': ids[1], 'fingerprintA': 'fp-0', 'fingerprintB': 'fp-1',
                             'relation': 'UNRELATED'}}
        vectors = {article_id: [1.0, 0.0] for article_id in ids[:3]}
        with patch.object(upgrade, 'vector_candidates', return_value=vectors):
            result = upgrade.lexical_candidates(catalog, editorial, relations)
        pairs = {tuple(sorted((row['id'], candidate['id'])))
                 for row in result['relations'] for candidate in row['candidates']}
        self.assertNotIn(tuple(sorted(ids[:2])), pairs)
        self.assertNotIn(tuple(sorted((ids[0], ids[3]))), pairs)
        self.assertTrue(pairs)

    def test_heat_deduplicates_publishers_and_uses_48h_half_life(self):
        at = self.now
        group = [
            {'id': 'a', 'eventKey': 'event-a', 'title': '最新标题', 'publishedAt': at.isoformat(),
             'sourceId': 'a1', 'source': 'A1', 'url': 'https://a.example/new'},
            {'id': 'b', 'eventKey': 'event-b', 'title': '较旧同机构报道',
             'publishedAt': (at - dt.timedelta(hours=1)).isoformat(),
             'sourceId': 'a2', 'source': 'A2', 'url': 'https://a.example/old'},
            {'id': 'c', 'eventKey': 'event-c', 'title': '另一机构',
             'publishedAt': (at - dt.timedelta(hours=24)).isoformat(),
             'sourceId': 'b1', 'source': 'B1', 'url': 'https://b.example/story'},
        ]
        sources = {'a1': {'publisherId': 'publisher-a'}, 'a2': {'publisherId': 'publisher-a'},
                   'b1': {'publisherId': 'publisher-b'}}
        result = upgrade.hot_ranking([group], sources, at)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['participants'], 2)
        self.assertEqual(result[0]['reports'], 3)
        self.assertEqual(result[0]['heat'], 15.0)
        self.assertEqual(result[0]['eventKey'], 'event-a')
        self.assertEqual(result[0]['title'], '最新标题')

    def test_article_extraction_blocks_nonpublic_targets(self):
        with patch.object(upgrade.socket, 'getaddrinfo', return_value=[
            (2, 1, 6, '', ('127.0.0.1', 443))
        ]):
            with self.assertRaises(ValueError):
                upgrade.public_url('https://public.example/article')

        with patch.object(upgrade.socket, 'getaddrinfo', return_value=[
            (2, 1, 6, '', ('93.184.216.34', 443))
        ]):
            parsed, address = upgrade.public_url('https://public.example/article')
        self.assertEqual(parsed.hostname, 'public.example')
        self.assertEqual(address, '93.184.216.34')

    def test_article_parser_drops_dangling_author_card_heading(self):
        paragraph = 'A substantial article paragraph describing an engineering decision. ' * 8
        parser = upgrade.ArticleHTML('https://example.com/article')
        parser.feed('<article><h1>Title</h1><p>' + paragraph + '</p><p>' + paragraph +
                    '</p><p>' + paragraph + '</p><h2>About the authors</h2></article>')
        region, body, paragraphs = parser.result()
        self.assertEqual(region, 'article')
        self.assertEqual(paragraphs, 3)
        self.assertFalse(body.endswith('About the authors'))

    def test_public_payload_never_reads_private_markdown_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / 'local'
            dist = root / 'dist'
            reading = local / 'reading'
            reading.mkdir(parents=True)
            private_marker = 'PRIVATE_READING_BODY_MUST_NOT_LEAK'
            (reading / f'{self.article_id}.md').write_text(private_marker, encoding='utf-8')
            editorial = {'id': self.article_id, 'selected': True, 'fingerprint': 'fingerprint-v1', 'title': '测试',
                         'summary': '公开摘要', 'why': '关注理由', 'caveat': '限制',
                         'category': '工程实践', 'themes': ['FDE'], 'basis': 'primary_article',
                         'evidence': [self.item['url']], 'eventKey': 'event-v1',
                         'reviewedAt': self.now.isoformat()}
            values = {
                'catalog.json': {self.article_id: self.item},
                'editorial.json': {self.article_id: editorial},
                'collection.json': {}, 'readings.json': {self.article_id: {
                    'fingerprint': 'fingerprint-v1', 'status': 'verified'}},
                'scores.json': {self.article_id + ':fingerprint-v1:' + upgrade.SCORE_VERSION: {
                    role: {'score': 80, 'contextId': 'test-context-' + role,
                           'standardVersion': upgrade.SCORE_VERSION, 'standardHash': 'a' * 64}
                    for role in ['A', 'B']}}, 'relations.json': {},
            }
            for name, value in values.items():
                (local / name).write_text(json.dumps(value), encoding='utf-8')
            with patch.object(news, 'LOCAL', local), patch.object(news, 'DIST', dist), \
                 patch.object(upgrade, 'LOCAL', local), patch.object(upgrade, 'READING', reading), \
                 patch.object(news, 'now', return_value=self.now.astimezone(news.TZ)):
                payload = news.public_payload()
            self.assertNotIn(private_marker, json.dumps(payload))
            self.assertEqual(payload['items'][0]['readingStatus'], 'verified')


if __name__ == '__main__':
    unittest.main()
