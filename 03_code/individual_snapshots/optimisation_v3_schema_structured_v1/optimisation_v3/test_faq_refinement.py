import unittest
from .arms import Source, Evidence
from .faq_refinement import question_for, refined_faq

class FaqRefinementTests(unittest.TestCase):
    def test_route_scope_question(self):
        s=Source('https://example.com/flights/a/b','','')
        e=Evidence('f',s.url,'',0,200,'Cheap Flights from Brisbane (BNE) to Auckland (AKL) from $505. Fees apply.','505','price','AUD')
        self.assertIn('Brisbane (BNE) to Auckland (AKL)',question_for(s,e)[0])
    def test_wrong_country_declined(self):
        s=Source('https://example.com/flights/au/th','','')
        e=Evidence('f',s.url,'',0,100,'Flights from the UK take 12 hours.','12','quantity','hours')
        self.assertEqual(question_for(s,e)[1],'geographical_scope_mismatch')
    def test_noop_preserves_bytes(self):
        s=Source('https://example.com','<html><body>Original.</body></html>','Original.')
        o=refined_faq(s,[])
        self.assertEqual((o['html'],o['clean']),(s.html,s.clean))
    def test_overlap_keeps_intact_largest_span(self):
        text='Cheap Flights from Brisbane to Auckland from $505. Displayed fares exclude fees. Fees are applied once at checkout.'
        s=Source('https://example.com','<html><body>'+text+'</body></html>',text)
        fs=[dict(fact_id=str(i),source_url=s.url,status='verified',verified_by='reviewer',verified_on='2026-09-12',claim=c,claim_type='price',value='505') for i,c in enumerate([text[:text.index(' Displayed')],text[:text.index(' Fees are')]])]
        o=refined_faq(s,fs)
        self.assertEqual(len(o['evidence']),1)
        self.assertIn('Fees are applied once at checkout.',o['evidence'][0]['quote'])
        self.assertEqual(o['evidence'][0]['quote'],s.clean[o['evidence'][0]['start']:o['evidence'][0]['end']])

if __name__=='__main__':unittest.main()
