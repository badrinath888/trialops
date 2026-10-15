import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api')); sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_journey import journey, export, rec, outcome, FILED, SUBJ, NOW, GOOD_PORTAL, link
from journey import evaluate
from priority import build_checks, build_candidates, rank, mapped_checks, would_cycle, RULE


def setup(outcomes=None, exports=None, links=()):
    j = journey(exports if exports is not None else [export(system='mock-binder-hub', stages=['transfer'], complete=True)], list(links))
    outs = [{**o, 'description': 'The same document/version is filed and visible in the intended binder.'} for o in (outcomes if outcomes is not None else [outcome(FILED)])]
    return j, outs, build_checks(j, outs, evaluate(outs, {}, j, SUBJ, list(links), NOW, None), None)


def cands(j, checks, corr=None, inputs=None, plan=None):
    c = build_candidates(j, checks, corr or {}, inputs or {}, plan or {})
    live, waiting = rank(c, checks)
    return {x['key']: x for x in live + waiting}, live, waiting


def inp(effort='unknown', pre=(), rev=1, note=''):
    return {'effort': effort, 'effort_note': note, 'prerequisites': list(pre), 'rev': rev}


class Ranking(unittest.TestCase):
    def test_request_maps_to_distinct_unresolved_checks_by_structured_rule(self):
        j, o, checks = setup()
        by, live, _ = cands(j, checks)
        g = by['no_record:destination_filing']
        self.assertEqual(g['unresolved'], sorted(['stage:destination_filing', 'outcome:%s:destination_filing:completed' % o[0]['id']]))
        self.assertIn('could help assess 2 checks', g['explanation'])
        self.assertNotIn('will resolve', g['explanation'].lower())
        from priority import RULE_TEXT; self.assertIn('does not guarantee', RULE_TEXT)
        self.assertEqual(g['target']['binder_ref'], 'BND-77'); self.assertEqual(g['target']['document_version'], '2')

    def test_corrections_add_remove_and_repeats_count_once(self):
        j, o, checks = setup()
        extra = 'outcome:%s:binder_visibility:visible' % o[0]['id']
        k = 'no_record:destination_filing'
        self.assertEqual(len(mapped_checks(k, 'destination_filing', checks, {(k, extra): 'add'})), 3)
        self.assertEqual(mapped_checks(k, 'destination_filing', checks, {(k, extra): 'add'}), mapped_checks(k, 'destination_filing', checks + [dict(checks[0])], {(k, extra): 'add', (k, 'stage:destination_filing'): 'add'}))
        self.assertNotIn('stage:destination_filing', mapped_checks(k, 'destination_filing', checks, {(k, 'stage:destination_filing'): 'remove'}))
        self.assertEqual(mapped_checks(k, 'destination_filing', checks, {(k, 'nope'): 'add'}), mapped_checks(k, 'destination_filing', checks, {}))  # unknown check ignored, never invented

    def test_resolved_and_inapplicable_checks_do_not_count(self):
        j, o, checks = setup([outcome(FILED, required=False)])
        by, _, _ = cands(j, checks)
        self.assertEqual(by['no_record:destination_filing']['unresolved'], ['stage:destination_filing'])
        self.assertTrue(by['no_record:destination_filing']['excluded'])
        j2, _, c2 = setup(exports=[export(*GOOD_PORTAL, system='mock-upload-portal', stages=['upload_receipt', 'processing'])])
        self.assertEqual([c['resolved'] for c in c2 if c['key'] in ('stage:upload_receipt', 'stage:processing')], [True, True])

    def test_order_coverage_then_effort_then_unknown_last_then_stable_key(self):
        j, o, checks = setup()
        corr = {('no_record:binder_visibility', 'stage:destination_filing'): 'add'}
        _, live, _ = cands(j, checks, corr)
        self.assertEqual(live[0]['key'], 'no_record:binder_visibility')  # 3 distinct checks beat 2
        j, _, checks = setup([])  # no outcomes: each gap maps to exactly its own stage check, so coverage ties
        inputs = {'no_record:transfer': inp('low'), 'no_record:destination_filing': inp('medium'), 'no_record:processing': inp('high')}
        by, live, _ = cands(j, checks, None, inputs)
        self.assertEqual([x['key'] for x in live], ['no_record:transfer', 'no_record:destination_filing', 'no_record:processing', 'no_record:binder_visibility', 'no_record:upload_receipt'])
        self.assertEqual(by['no_record:upload_receipt']['effort'], 'unknown')  # never invented
        from priority import RULE_TEXT; self.assertIn('effort not estimated', by['no_record:upload_receipt']['explanation']); self.assertIn('not assumed to be high', RULE_TEXT)
        _, again, _ = cands(j, checks, None, inputs)
        self.assertEqual([x['key'] for x in live], [x['key'] for x in again])

    def test_blocked_by_unmet_prerequisite_sorts_after_ready_even_with_more_coverage(self):
        j, o, checks = setup()
        dep = {'kind': 'gap', 'key': 'no_record:transfer', 'stage': 'transfer'}
        by, live, _ = cands(j, checks, None, {'no_record:destination_filing': inp('low', [dep])})
        f = by['no_record:destination_filing']
        self.assertEqual(f['state'], 'blocked')
        self.assertGreater(f['rank'], by['no_record:transfer']['rank'])
        self.assertIn('blocked until 1 prerequisite is met', f['explanation'])
        # prerequisite satisfied once its gap is resolved by evidence
        j2, _, c2 = setup(exports=[export(rec('transfer', 'mock-binder-hub', 'J', 3, document_ref='DOC-5001', version='2', binder_ref='BND-77', status='completed'), system='mock-binder-hub')], links=[link('document', 'mock-binder-hub', 'DOC-5001')])
        by2, _, _ = cands(j2, c2, None, {'no_record:destination_filing': inp('low', [dep])})
        self.assertEqual(by2['no_record:destination_filing']['prerequisites'][0]['state'], 'met')
        self.assertEqual(by2['no_record:destination_filing']['state'], 'ready')

    def test_check_prerequisite_uses_check_state_and_vanished_ones_stay_blocked(self):
        j, o, checks = setup()
        pre = {'kind': 'check', 'key': 'stage:transfer'}
        by, _, _ = cands(j, checks, None, {'no_record:destination_filing': inp('low', [pre])})
        self.assertEqual(by['no_record:destination_filing']['state'], 'blocked')  # an unresolved check blocks; a received response alone would not change this
        gone = {'kind': 'check', 'key': 'outcome:deleted:transfer:completed'}
        by, _, _ = cands(j, checks, None, {'no_record:destination_filing': inp('low', [gone])})
        self.assertEqual((by['no_record:destination_filing']['prerequisites'][0]['state'], by['no_record:destination_filing']['state']), ('unmatched', 'blocked'))
        self.assertIn('no longer matches', by['no_record:destination_filing']['explanation'])
        gone_gap = {'kind': 'gap', 'key': 'no_record:vanished', 'stage': 'processing'}  # vanished gap whose stage is not verified is not satisfied
        by, _, _ = cands(j, checks, None, {'no_record:destination_filing': inp('low', [gone_gap])})
        self.assertEqual(by['no_record:destination_filing']['state'], 'blocked')
        self.assertEqual(cands(j, checks, None, {'no_record:destination_filing': inp('low', [])})[0]['no_record:destination_filing']['state'], 'ready')  # explicit removal unblocks

    def test_outcome_check_labels_show_name_and_short_stable_id_without_changing_keys(self):
        j, o, checks = setup([outcome(FILED), outcome(FILED)])
        labels = [c['label'] for c in checks if c['key'].startswith('outcome:')]
        self.assertEqual(len(labels), len(set(labels)))
        for x in o:
            self.assertTrue(any('#' + str(x['outcome_key'])[:8] in l and 'filed and visible' in l for l in labels))
        self.assertTrue(all(any(c['key'].startswith('outcome:%s:' % x['id']) for x in o) for c in checks if c['key'].startswith('outcome:')))  # keys still use the exact outcome revision id

    def test_cycle_detection(self):
        self.assertTrue(would_cycle({'b': ['c'], 'c': ['a']}, 'a', ['b']))
        self.assertTrue(would_cycle({}, 'a', ['a']))
        self.assertFalse(would_cycle({'b': ['c'], 'c': []}, 'a', ['b']))

    def test_sent_requests_wait_and_drafts_stay_openable(self):
        j, o, checks = setup()
        item = lambda st: {'id': 'p1', 'request_id': 'r1', 'request_status': st, 'question': 'Q'}
        by, live, waiting = cands(j, checks, None, None, {'no_record:transfer': item('requested'), 'no_record:processing': item('received'), 'no_record:destination_filing': item('draft')})
        self.assertEqual((by['no_record:transfer']['state'], by['no_record:processing']['state'], by['no_record:destination_filing']['state']), ('waiting', 'received', 'ready'))
        self.assertNotIn('no_record:transfer', [x['key'] for x in live]); self.assertIsNone(by['no_record:transfer']['rank'])
        self.assertTrue(by['no_record:destination_filing']['existing']['request_id'] == 'r1')
        self.assertIn('not counted as assessed', by['no_record:processing']['explanation'])
        self.assertEqual(by['no_record:processing']['unresolved'], by['no_record:processing']['unresolved'])  # receiving a response never resolves a check

    def test_rule_version_is_fixed(self):
        self.assertEqual(RULE, 'suggested-order-1')


if __name__ == '__main__':
    unittest.main()
