import unittest
from dataclasses import asdict
from bs4 import BeautifulSoup
from optimisation_v3.arms import *

class ArmChecks(unittest.TestCase):
    def test_exact_amount_and_body(self):
        for raw in ['<head><title>Flights from $150</title></head><body>Text</body>',
                    '<body><p>Flights from $150.99</p></body>',
                    '<body><p>Flight booking fee $150</p></body>',
                    '<body><p>Flights from USD $150</p></body>',
                    '<body><div hidden><p>Flights from $150</p></div></body>']:
            self.assertIsNone(fare_node(BeautifulSoup(raw,'html.parser'),'150'))
        self.assertIsNotNone(fare_node(BeautifulSoup('<body><p>Flights from $1,299</p></body>','html.parser'),'1299'))
    def test_unknown_claim_rejected(self):
        with self.assertRaises(ValueError):validate_evidence(Source('u','','text'),[{'fact_id':'invented'}],[])
    def test_qualifiers_preserved(self):
        text='Flights from $150. Fares exclude booking fees. Fees are applied at checkout.'
        s=Source('u','<body><p>'+text+'</p></body>',text)
        facts=[dict(fact_id='1',status='verified',verified_by='Reviewer',verified_on='2026-08-20',source_url='u',claim='Flights from $150. Fares exclude',value='150',claim_type='price',unit='AUD')]
        q=quoted(s,facts,'fare_clarification')
        self.assertTrue(q['notes']['inserted']);self.assertIn('Fares exclude booking fees.',q['evidence'][0]['quote'])
        validate_output(q,quoted(s,facts,'fare_clarification'))
        with self.assertRaises(ValueError):validate_output({**q,'clean':'Invented $999999'},q)
    def test_noop_exact(self):
        s=Source('u','<body>Text</body>','frozen representation')
        for arm in ('page_grounded_faq','fare_clarification'):
            o=quoted(s,[],arm);self.assertEqual(o['clean'],s.clean);self.assertEqual(o['html'],s.html)
    def test_render_integrity_and_no_digit_repair(self):
        s=Source('https://example.com/page','<body>old</body>','old')
        raw=('<html><head><title>Travel</title><link rel="canonical" href="https://example.com/page"></head><body>'+
             'Travel information '*101+'$150 2 adults</body></html>').encode()
        meta=dict(status='ok',url=s.url,sha256=hashlib.sha256(raw).hexdigest(),rendered_at='2026-08-26')
        o=rendered(s,raw,meta);self.assertIn('$150 2 adults',o['clean'])
        for bad in [{**meta,'url':'https://wrong.example/'},{**meta,'sha256':'wrong'}]:
            with self.assertRaises(ValueError):rendered(s,raw,bad)
        with self.assertRaises(ValueError):validate_output({**o,'html':'changed'},o)
    def test_fact_scope_status_and_offsets(self):
        s=Source('u','<body>Flights from $150.</body>','Flights from $150. Conditions apply to travel dates.')
        f=dict(fact_id='1',status='verified',verified_by='Reviewer',verified_on='2026-08-20',source_url='u',claim='Flights from $150. Conditions',value='150',claim_type='price')
        self.assertEqual(len(evidence(s,[f])),1)
        for change in [dict(source_url='other'),dict(status='candidate'),dict(verified_by=''),dict(claim='Unsupported fare claim')]:
            self.assertEqual(evidence(s,[{**f,**change}]),[])
        e=asdict(evidence(s,[f])[0]);e['quote']='Changed $99999'
        with self.assertRaises(ValueError):validate_evidence(s,[e],[f])
        with self.assertRaises(ValueError):evidence(s,[f,f])

if __name__=='__main__':unittest.main()
