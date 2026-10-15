import sys, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from journey import normalize_export, build_journey, evaluate, overall, example_export, valid_requirements, STAGES

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
T = lambda h: (NOW - timedelta(hours=h)).isoformat()
SUBJ = dict(rev=1, document_system='mock-upload-portal', document_ref='DOC-5001', document_version='2', destination_system='mock-binder-hub', binder_ref='BND-77')
REC = dict(document_ref=None, version=None, transfer_ref=None, binder_ref=None, xref_system=None, xref_ref=None, status=None, status_raw=None, raw={})
_n = [0]


def rec(stage, system, ref, hours_ago=1, **kw):
    _n[0] += 1
    return {**REC, 'stage': stage, 'source_system': system, 'source_ref': ref, 'observed_at': T(hours_ago), 'index': _n[0], **kw}


def export(*records, system='mock-binder-hub', complete=True, stages=STAGES, n=[0]):
    n[0] += 1
    return {'id': 'e%d-%s' % (n[0], system), 'source_system': system, 'export_ref': 'X%d' % n[0], 'observed_at': T(0), 'created_at': NOW,
            'coverage': {'complete': complete, 'stages': list(stages), 'from': None, 'to': None}, 'records': list(records)}


def link(kind, fs, fr, ts='mock-upload-portal', tr='DOC-5001', revoked=None):
    return {'id': 'L-' + fr, 'kind': kind, 'from_system': fs, 'from_ref': fr, 'to_system': ts, 'to_ref': tr, 'revoked_at': revoked, 'rationale': 'Reviewed job log', 'evidence': 'Job log line', 'actor_name': 'R', 'created_at': NOW}


def journey(exports, links=(), hours=None):
    return build_journey(SUBJ, list(links), exports, hours, NOW)


def stage(j, name):
    return next(s for s in j['stages'] if s['stage'] == name)


GOOD_PORTAL = [rec('upload_receipt', 'mock-upload-portal', 'RCPT-1', 5, document_ref='DOC-5001', version='2', status='received'),
               rec('processing', 'mock-upload-portal', 'PROC-1', 4, document_ref='DOC-5001', version='2', status='completed')]


class Matching(unittest.TestCase):
    def test_upload_pending_and_failed_sync_unlinked_leaves_transfer_unknown(self):
        j = journey([export(rec('upload_receipt', 'mock-upload-portal', 'RCPT-1', 5, document_ref='DOC-5001', version='2', status='received'),
                            rec('processing', 'mock-upload-portal', 'PROC-1', 4, document_ref='DOC-5001', version='2', status='pending'),
                            rec('transfer', 'mock-binder-hub', 'JOB-9', 3, status='failed'))])
        self.assertEqual((stage(j, 'upload_receipt')['assessment'], stage(j, 'processing')['operational_status']), ('verified', 'pending'))
        t = stage(j, 'transfer')
        self.assertEqual(t['assessment'], 'unknown')
        self.assertIsNone(t['operational_status'])
        self.assertEqual(t['candidates'][0]['problems'], ['unlinked'])
        self.assertTrue(any(g['code'] == 'unlinked' for g in t['gaps']))

    def test_completed_processing_without_destination_evidence_requests_exact_records(self):
        j = journey([export(*GOOD_PORTAL, system='mock-upload-portal', stages=STAGES[:2])])
        f = stage(j, 'destination_filing')
        self.assertEqual(f['assessment'], 'unknown')
        gap = f['gaps'][0]
        self.assertEqual(gap['code'], 'no_record')
        for needle in ('DOC-5001', 'version 2', 'BND-77', 'mock-binder-hub'):
            self.assertIn(needle, gap['question'] + gap['description'])
        self.assertIn('No imported export declares coverage', ' '.join(f['missing']))

    def test_exact_linked_failure_is_supported_failure_not_root_cause(self):
        r = rec('transfer', 'mock-binder-hub', 'JOB-9', 3, status='failed')
        j = journey([export(r)], [link('record', 'mock-binder-hub', 'JOB-9')])
        t = stage(j, 'transfer')
        self.assertEqual((t['assessment'], t['operational_status']), ('verified', 'failed'))
        self.assertEqual(t['records'][0]['match_basis'], 'reviewer_link')
        self.assertEqual(t['records'][0]['link']['rationale'], 'Reviewed job log')
        self.assertIn('root cause is not established', ' '.join(t['notes']))

    def test_revoked_link_no_longer_matches(self):
        j = journey([export(rec('transfer', 'mock-binder-hub', 'JOB-9', 3, status='failed'))], [link('record', 'mock-binder-hub', 'JOB-9', revoked=NOW)])
        self.assertEqual(stage(j, 'transfer')['assessment'], 'unknown')

    def test_same_id_text_in_another_system_is_a_collision_until_mapped(self):
        r = rec('destination_filing', 'mock-binder-hub', 'FILE-1', 2, document_ref='DOC-5001', version='2', binder_ref='BND-77', status='completed')
        j = journey([export(r)])
        f = stage(j, 'destination_filing')
        self.assertEqual((f['assessment'], f['candidates'][0]['problems']), ('unknown', ['id_collision']))
        j = journey([export(r)], [link('document', 'mock-binder-hub', 'DOC-5001')])
        self.assertEqual(stage(j, 'destination_filing')['assessment'], 'verified')

    def test_source_declared_cross_reference_is_explicit_mapping(self):
        r = rec('destination_filing', 'mock-binder-hub', 'FILE-1', 2, document_ref='HUB-1', xref_system='mock-upload-portal', xref_ref='DOC-5001', version='2', binder_ref='BND-77', status='completed')
        f = stage(journey([export(r)]), 'destination_filing')
        self.assertEqual((f['assessment'], f['records'][0]['match_basis']), ('verified', 'source_declared'))

    def test_wrong_version_and_wrong_or_unmapped_binder_do_not_match(self):
        base = dict(document_ref='DOC-5001', status='completed')
        wrong_v = rec('destination_filing', 'mock-upload-portal', 'F1', 2, version='1', binder_ref='BND-77', **base)
        # destination system is mock-binder-hub, so a portal record naming BND-77 is a destination collision
        self.assertIn('destination_collision', stage(journey([export(wrong_v, system='mock-upload-portal')]), 'destination_filing')['candidates'][0]['problems'])
        v1 = rec('destination_filing', 'mock-binder-hub', 'F2', 2, document_ref='DOC-5001', version='1', binder_ref='BND-77', status='completed')
        f = stage(journey([export(v1)], [link('document', 'mock-binder-hub', 'DOC-5001')]), 'destination_filing')
        self.assertEqual((f['assessment'], f['candidates'][0]['problems']), ('unknown', ['wrong_version']))
        wb = rec('destination_filing', 'mock-binder-hub', 'F3', 2, document_ref='DOC-5001', version='2', binder_ref='BND-99', status='completed')
        f = stage(journey([export(wb)], [link('document', 'mock-binder-hub', 'DOC-5001')]), 'destination_filing')
        self.assertEqual((f['assessment'], f['candidates'][0]['problems']), ('unknown', ['wrong_destination']))

    def test_conflicting_sources_are_preserved_not_resolved_by_recency(self):
        a = rec('processing', 'mock-upload-portal', 'P1', 5, document_ref='DOC-5001', version='2', status='completed')
        b = rec('processing', 'mock-binder-hub', 'P2', 1, document_ref='H', xref_system='mock-upload-portal', xref_ref='DOC-5001', version='2', status='failed')
        p = stage(journey([export(a, system='mock-upload-portal'), export(b)]), 'processing')
        self.assertEqual((p['assessment'], p['operational_status']), ('conflicting', None))
        self.assertEqual(len(p['records']), 2)
        self.assertIn('not treated as truth', p['conflicts'][0])

    def test_same_system_progression_is_not_a_conflict(self):
        a = rec('processing', 'mock-upload-portal', 'P1', 5, document_ref='DOC-5001', version='2', status='pending')
        b = rec('processing', 'mock-upload-portal', 'P1', 1, document_ref='DOC-5001', version='2', status='completed')
        p = stage(journey([export(a, b, system='mock-upload-portal')]), 'processing')
        self.assertEqual((p['assessment'], p['operational_status'], p['earlier_observations']), ('verified', 'completed', 1))

    def test_incomplete_export_absence_is_not_evidence(self):
        f = stage(journey([export(system='mock-binder-hub', complete=False, stages=['destination_filing'])]), 'destination_filing')
        self.assertEqual((f['assessment'], f['gaps'][0]['code']), ('unknown', 'export_incomplete'))
        self.assertIn('not evidence', ' '.join(f['missing']))
        c = stage(journey([export(system='mock-binder-hub', complete=True, stages=['destination_filing'])]), 'destination_filing')
        self.assertIn('does not establish a failure', ' '.join(c['missing']))
        self.assertIsNone(c['operational_status'])


def outcome(reqs, remediation_hours=6, required=True, n=[0]):
    n[0] += 1
    return {'id': 'o%d' % n[0], 'outcome_key': 'k%d' % n[0], 'rev': 1, 'required': required, 'requirements': reqs, 'remediation_at': T(remediation_hours)}


FILED = [{'stage': 'destination_filing', 'status': 'completed'}, {'stage': 'binder_visibility', 'status': 'visible'}]


def good_hub(hours_ago=1, **over):
    kw = dict(document_ref='DOC-5001', version='2', binder_ref='BND-77')
    return [rec('destination_filing', 'mock-binder-hub', 'F1', hours_ago, status='completed', **kw), rec('binder_visibility', 'mock-binder-hub', 'V1', hours_ago, status='visible', **kw)]


class Verification(unittest.TestCase):
    def run_outcome(self, o, exports, links=(), hours=None, human=None):
        j = journey(exports, links, hours)
        r = evaluate([o], human or {}, j, SUBJ, list(links), NOW, hours)
        return r, overall(r)

    def test_exact_version_filing_and_visibility_after_remediation_verifies(self):
        r, o = self.run_outcome(outcome(FILED), [export(*good_hub())], [link('document', 'mock-binder-hub', 'DOC-5001')])
        self.assertEqual((r[0]['result'], o), ('verified', 'verified'))
        self.assertEqual(r[0]['parts'][0]['before'], [])

    def test_pre_remediation_observation_does_not_verify(self):
        r, o = self.run_outcome(outcome(FILED, remediation_hours=1), [export(*good_hub(hours_ago=3))], [link('document', 'mock-binder-hub', 'DOC-5001')])
        self.assertEqual((r[0]['result'], o), ('insufficient', 'insufficient_evidence'))
        self.assertEqual(len(r[0]['parts'][0]['before']), 1)

    def test_stale_by_configured_policy_only(self):
        ex, lk = [export(*good_hub(hours_ago=5))], [link('document', 'mock-binder-hub', 'DOC-5001')]
        self.assertEqual(self.run_outcome(outcome(FILED), ex, lk, hours=2)[0][0]['result'], 'insufficient')
        self.assertEqual(self.run_outcome(outcome(FILED), ex, lk, hours=None)[0][0]['result'], 'verified')

    def test_wrong_version_or_binder_is_not_verified(self):
        for over in (dict(version='1'), dict(binder_ref='BND-99')):
            recs = [rec(s, 'mock-binder-hub', 'X' + s, 1, document_ref='DOC-5001', **{**dict(version='2', binder_ref='BND-77', status='completed' if s == 'destination_filing' else 'visible'), **over}) for s in ('destination_filing', 'binder_visibility')]
            r, o = self.run_outcome(outcome(FILED), [export(*recs)], [link('document', 'mock-binder-hub', 'DOC-5001')])
            self.assertEqual((r[0]['result'], o), ('insufficient', 'insufficient_evidence'), over)

    def test_unmapped_identical_id_does_not_verify(self):
        self.assertEqual(self.run_outcome(outcome(FILED), [export(*good_hub())])[0][0]['result'], 'insufficient')

    def test_contrary_exact_record_contradicts_and_overall_not_verified(self):
        recs = good_hub()
        recs[1]['status'] = 'not_visible'
        r, o = self.run_outcome(outcome(FILED), [export(*recs)], [link('document', 'mock-binder-hub', 'DOC-5001')])
        self.assertEqual((r[0]['result'], o), ('contradicted', 'not_verified'))

    def test_conflicting_post_remediation_sources_are_insufficient(self):
        other = rec('binder_visibility', 'mock-upload-portal', 'V2', 1, document_ref='DOC-5001', version='2', binder_ref='BND-77', status='not_visible')
        # portal is not the destination system, so its binder text is an unmapped collision and cannot contradict
        r, _ = self.run_outcome(outcome(FILED), [export(*good_hub()), export(other, system='mock-upload-portal')], [link('document', 'mock-binder-hub', 'DOC-5001')])
        self.assertEqual(r[0]['result'], 'verified')
        mapped = rec('binder_visibility', 'mock-binder-hub', 'V3', 1, document_ref='DOC-5001', version='2', binder_ref='BND-77', status='not_visible')
        r, _ = self.run_outcome(outcome(FILED), [export(*good_hub()[:1], mapped)], [link('document', 'mock-binder-hub', 'DOC-5001')])
        self.assertEqual(r[0]['result'], 'contradicted')

    def test_human_only_outcome_needs_human_assessment_and_is_never_silently_satisfied(self):
        o = outcome(None)
        r, ov = self.run_outcome(o, [export()])
        self.assertEqual((r[0]['method'], r[0]['result'], ov), ('needs_human_assessment', 'insufficient', 'insufficient_evidence'))
        r, ov = self.run_outcome(o, [export()], human={o['id']: {'result': 'verified', 'rationale': 'Checked the binder myself'}})
        self.assertEqual((r[0]['method'], ov), ('human', 'verified'))

    def test_overall_matrix(self):
        mk = lambda *rs: [{'required': True, 'result': x} for x in rs]
        self.assertEqual(overall(mk('verified', 'verified')), 'verified')
        self.assertEqual(overall(mk('verified', 'contradicted', 'insufficient')), 'not_verified')
        self.assertEqual(overall(mk('verified', 'insufficient')), 'partially_verified')
        self.assertEqual(overall(mk('insufficient', 'insufficient')), 'insufficient_evidence')
        self.assertEqual(overall([]), 'insufficient_evidence')
        self.assertEqual(overall([{'required': False, 'result': 'verified'}]), 'insufficient_evidence')
        self.assertEqual(overall(mk('verified') + [{'required': False, 'result': 'contradicted'}]), 'verified')

    def test_requirements_validated(self):
        for bad in ([], [{'stage': 'transfer', 'status': 'visible'}], [{'stage': 'nope', 'status': 'completed'}], [{'stage': 'transfer', 'status': 'completed', 'x': 1}]):
            with self.assertRaises(ValueError):
                valid_requirements(bad)
        self.assertIsNone(valid_requirements(None))

    def test_fingerprint_tracks_evidence_and_links_not_clock(self):
        ex = [export(*good_hub())]
        a, b = journey(ex), build_journey(SUBJ, [], ex, None, NOW + timedelta(hours=9))
        self.assertEqual(a['fingerprint'], b['fingerprint'])
        self.assertNotEqual(a['fingerprint'], journey(ex, [link('document', 'mock-binder-hub', 'DOC-5001')])['fingerprint'])


class Semantics(unittest.TestCase):
    """Insufficient = intended document/destination unknown or not yet in the required state; Contradicted = explicit negative on the exact document/version/binder."""
    def one(self, recs, links=(), reqs=None):
        j = journey([export(*recs)], links)
        return evaluate([outcome(reqs or FILED)], {}, j, SUBJ, list(links), NOW, None)[0]

    def test_wrong_version_or_binder_never_verifies_or_contradicts_even_with_negative_status(self):
        lk = [link('document', 'mock-binder-hub', 'DOC-5001')]
        for stat_f, stat_v in (('completed', 'visible'), ('failed', 'not_visible')):
            for over in (dict(version='1'), dict(binder_ref='BND-99')):
                recs = [rec(s, 'mock-binder-hub', 'W' + s, 1, document_ref='DOC-5001', **{**dict(version='2', binder_ref='BND-77', status=stat_f if s == 'destination_filing' else stat_v), **over}) for s in ('destination_filing', 'binder_visibility')]
                self.assertEqual(self.one(recs, lk)['result'], 'insufficient', (over, stat_f))

    def test_unknown_destination_or_unmapped_document_is_insufficient_not_contradicted(self):
        lk = [link('document', 'mock-binder-hub', 'DOC-5001')]
        nodest = [rec('binder_visibility', 'mock-binder-hub', 'V', 1, document_ref='DOC-5001', version='2', status='not_visible')]
        self.assertEqual(self.one(nodest, lk, FILED[1:])['result'], 'insufficient')
        unmapped = [rec('binder_visibility', 'mock-binder-hub', 'V', 1, document_ref='DOC-5001', version='2', binder_ref='BND-77', status='not_visible')]
        self.assertEqual(self.one(unmapped, [], FILED[1:])['result'], 'insufficient')

    def test_non_negative_mismatch_such_as_pending_is_insufficient(self):
        lk = [link('document', 'mock-binder-hub', 'DOC-5001')]
        pend = [rec('destination_filing', 'mock-binder-hub', 'F', 1, document_ref='DOC-5001', version='2', binder_ref='BND-77', status='pending')]
        r = self.one(pend, lk, FILED[:1])
        self.assertEqual(r['result'], 'insufficient')
        self.assertIn('neither confirms nor contradicts', r['parts'][0]['reason'])

    def test_explicit_negative_on_exact_record_contradicts(self):
        lk = [link('document', 'mock-binder-hub', 'DOC-5001')]
        neg = [rec('destination_filing', 'mock-binder-hub', 'F', 1, document_ref='DOC-5001', version='2', binder_ref='BND-77', status='failed')]
        self.assertEqual(self.one(neg, lk, FILED[:1])['result'], 'contradicted')

    def test_reviewed_response_attestation_is_context_only(self):
        att = {**REC, 'stage': 'destination_filing', 'source_system': 'mock-binder-hub', 'source_ref': 'FILE-A', 'document_ref': 'DOC-5001', 'version': '2', 'binder_ref': 'BND-77', 'status': 'completed',
               'status_raw': 'completed', 'observed_at': T(1), 'export_ref': 'external:x', 'export_complete': None, 'ref': 'att:1', 'index': 0, 'attested_by': 'R', 'response_ref': 'external:x'}
        lk = [link('document', 'mock-binder-hub', 'DOC-5001')]
        j = build_journey(SUBJ, lk, [], None, NOW, [att])
        f = stage(j, 'destination_filing')
        self.assertEqual((f['assessment'], f['operational_status'], len(f['attested'])), ('unknown', None, 1))
        self.assertIn('no system record supports it', ' '.join(f['missing']))
        self.assertEqual(evaluate([outcome(FILED[:1])], {}, j, SUBJ, lk, NOW, None)[0]['result'], 'insufficient')
        self.assertNotEqual(j['fingerprint'], build_journey(SUBJ, lk, [], None, NOW)['fingerprint'])


class Import(unittest.TestCase):
    def test_two_differently_shaped_examples_normalize_with_provenance(self):
        for shape, system, n in (('portal', 'mock-upload-portal', 2), ('hub', 'mock-binder-hub', 3)):
            ex = example_export(shape, 'CT-204', 'SITE-104', observed_at=NOW)
            out = normalize_export(ex['export'], ex['mapping'], NOW + timedelta(seconds=1))
            self.assertEqual((out['source_system'], len(out['records'])), (system, n))
            r = out['records'][0]
            self.assertEqual(r['raw'], ex['export']['rows'][0])
            self.assertTrue(r['source_ref'] and r['version'] == '2' and r['document_ref'] == 'DOC-5001')
        self.assertEqual(normalize_export(*[example_export('hub', 'S', 'T', observed_at=NOW)[k] for k in ('export', 'mapping')], NOW)['records'][0]['binder_ref'], 'BND-77')

    def test_rejections(self):
        def bad(mut):
            ex = example_export('portal', 'CT-204', 'SITE-104', observed_at=NOW)
            mut(ex['export'], ex['mapping'])
            with self.assertRaises(ValueError):
                normalize_export(ex['export'], ex['mapping'], NOW + timedelta(seconds=1))
        bad(lambda e, m: e.update(synthetic=False))
        bad(lambda e, m: e.update(observed_at=(NOW + timedelta(days=1)).isoformat()))
        bad(lambda e, m: e['rows'][0].update(at=(NOW + timedelta(hours=1)).isoformat()))
        bad(lambda e, m: e['rows'][0].update(doc_id='DOC-5001 filed in 3 minutes'))
        bad(lambda e, m: e['rows'][0].update(event='UNKNOWN'))
        bad(lambda e, m: e['coverage'].update(stages=['upload_receipt']))
        bad(lambda e, m: m['status_values'].update(RECEIVED='visible'))
        bad(lambda e, m: e['coverage'].update(complete='yes'))
        bad(lambda e, m: m['fields'].update(note='free_text'))

    def test_free_text_is_retained_but_never_parsed(self):
        ex = example_export('portal', 'CT-204', 'SITE-104', observed_at=NOW)
        ex['export']['rows'][0]['comment'] = 'DOC-9999 version 7 filed in BND-1 after 3 minutes, status completed'
        r = normalize_export(ex['export'], ex['mapping'], NOW + timedelta(seconds=1))['records'][0]
        self.assertEqual((r['document_ref'], r['version'], r['binder_ref'], r['status']), ('DOC-5001', '2', None, 'received'))
        self.assertIn('DOC-9999', r['raw']['comment'])

    def test_unmapped_status_stays_unrecorded(self):
        ex = example_export('portal', 'CT-204', 'SITE-104', observed_at=NOW)
        ex['export']['rows'][0]['state'] = 'MYSTERY'
        r = normalize_export(ex['export'], ex['mapping'], NOW + timedelta(seconds=1))['records'][0]
        self.assertEqual((r['status'], r['status_raw']), (None, 'MYSTERY'))


if __name__ == '__main__':
    unittest.main()
