import unittest,tempfile,json,hashlib
from pathlib import Path
from optimisation_v3.arms import Source,validate_output
from optimisation_v3.remaining import *

class RemainingChecks(unittest.TestCase):
    def external(self):
        return load_external(Path('data/optimisation_v3_sources/sydney_airport_2025'))
    def test_entity_boundaries(self):
        for text in ['BANANAS','Sydney holidays','NotSydney Airportish']:
            self.assertIsNone(entity_match(Source('u','',text)))
        for text in ['Sydney Airport','Flights from Sydney (SYD)']:
            self.assertIsNotNone(entity_match(Source('u','',text)))
    def test_exact_dose(self):
        for n in [1,10,33,100,1066]:
            text=' '.join(['word']*n);s=Source('u','<body><p>'+text+'</p></body>',text)
            o=oracle_repetition(s,['one two three four five six seven eight nine ten eleven twelve thirteen fourteen'])
            self.assertEqual(o['notes']['requested_extra_words'],o['notes']['actual_extra_words'])
            self.assertEqual(len(o['clean'].split())-n,o['notes']['actual_extra_words'])
    def test_attribution_comparator_preserves_fact(self):
        ext=self.external();s=Source('u','<body>Sydney Airport</body>','Sydney Airport')
        yes=attribution(s,ext);no=attribution(s,ext,False)
        self.assertEqual(yes['evidence'],no['evidence']);self.assertIn(ext.quote,yes['clean']);self.assertIn(ext.quote,no['clean'])
        self.assertIn(ext.source_url,yes['clean']);self.assertNotIn(ext.source_url,no['clean'])
    def test_combined_eligibility_original(self):
        ext=self.external();s=Source('u','<body>Sydney holidays</body>','Sydney holidays')
        o=combined(s,[],ext);self.assertEqual(o['clean'],s.clean)
        self.assertFalse(o['notes']['uses_llm']);self.assertFalse(o['notes']['citation_inserted'])
    def test_source_tamper(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for name in ['raw.html','meta.json','text.txt']:shutil.copy2(Path('data/optimisation_v3_sources/sydney_airport_2025')/name,p/name)
            meta=json.loads((p/'meta.json').read_text());meta['quote']='An unsupported claim';(p/'meta.json').write_text(json.dumps(meta))
            with self.assertRaises(ValueError):load_external(p)
    def test_padding_retired(self):
        with self.assertRaisesRegex(ValueError,'retired'):retired_padding()
    def test_forged_external_claim_rejected(self):
        from dataclasses import replace
        ext=replace(self.external(),quote='Sydney Airport sells flights for $1.')
        s=Source('u','<body>Sydney Airport</body>','Sydney Airport');o=attribution(s,ext)
        with self.assertRaises(ValueError):validate_research_output(s,o,[],Path('data/optimisation_v3_sources/sydney_airport_2025'),[])

if __name__=='__main__':unittest.main()
