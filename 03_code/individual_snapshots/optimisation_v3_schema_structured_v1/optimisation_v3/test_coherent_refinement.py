import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup
from optimisation_v3.test_rendered_organisation import OrganisationChecks
from optimisation_v3.coherent_refinement import coherent_rendered, useful_external
from optimisation_v3.arms import Source, cleaned
from optimisation_v3 import experiment

class CoherenceChecks(unittest.TestCase):
    def test_complete_faq_precedes_intact_offers_and_contents_resolves(self):
        args=OrganisationChecks().fixture(explanation_id='mc-faqs-section')
        out=coherent_rendered(*args)
        self.assertLess(out['clean'].index('Journey explanation'),out['clean'].index('Qantas $219*'))
        soup=BeautifulSoup(out['html'],'html.parser')
        self.assertIsNotNone(soup.find(id=soup.select_one('[data-geo-contents] a')['href'][1:]))
        self.assertIn('Fares exclude booking fees.',out['clean'])

    def test_external_preserves_original_and_requires_airport_evidence(self):
        raw='<html><body><main><h1>Sydney flights</h1><p>Sydney Airport details.</p><div data-testid="AlertBody">Fees are applied once at checkout.</div></main></body></html>'
        s=Source('https://www.flightcentre.com.au/flights/sydney',raw,cleaned(raw))
        e={'quote':'Sydney Airport is located just 13 minutes by train from the city.', 'source_url':'https://www.sydneyairport.com.au/info-sheet/transport-options'}
        out=useful_external(s,e)
        soup=BeautifulSoup(out['html'],'html.parser');soup.find(id='geo-external-useful').decompose()
        self.assertEqual(cleaned(str(soup)),s.clean)
        self.assertLess(out['clean'].index('Fees are applied once'),out['clean'].index('13 minutes'))
        no=Source(s.url,raw.replace('Sydney Airport','Other airport'),s.clean.replace('Sydney Airport','Other airport'))
        self.assertFalse(useful_external(no,e)['notes']['inserted'])

    def test_fresh_report_never_appends_historical_control(self):
        root=Path(__file__).resolve().parents[1]
        record=json.loads((root/'results/baseline_v2_1_repeat_20260909/records/Q01_reindexed_s1_r1.json').read_text())
        with tempfile.TemporaryDirectory() as name:
            out=Path(name);jobs=[]
            for arm in ('baseline_repeat','test_treatment'):
                j={'arm':arm,'path':arm+'.json','pair_key':'one','key':arm}
                jobs.append(j);(out/j['path']).write_text('{}')
            (out/'schedule.json').write_text(json.dumps(jobs));(out/'contexts.json').write_text('{}')
            lock={'parent_path':str(out/'nonexistent_parent'),'experiment_id':'test','control_generation':'fresh_interleaved'}
            def rec(_out,j,*args):return {**record,**j}
            with patch.object(experiment,'validate',return_value=lock),patch.object(experiment,'load_queries',return_value=[]),patch.object(experiment,'checked_record',side_effect=rec),patch.object(experiment.base,'validate_package',return_value={}):
                experiment.report(out)
            summary=json.loads((out/'summary.json').read_text())
            self.assertEqual(summary['control_records'],1)
            self.assertEqual(summary['records'],1)
            self.assertEqual(summary['scheduled_records'],2)
            self.assertTrue(summary['complete'])

if __name__=='__main__':unittest.main()
