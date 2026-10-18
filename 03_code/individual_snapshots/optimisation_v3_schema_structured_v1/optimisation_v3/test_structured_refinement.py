import unittest
from .arms import Source,ACTIVE,RETIRED
from .structured_refinement import refined_structured

class StructuredTests(unittest.TestCase):
    def build(self,tail=''):
        t='Cheap Flights from Brisbane (BNE) to Auckland (AKL) from $505 Flights from Brisbane to Auckland $505 ^ Hot deals for a Auckland getaway! Displayed fares exclude Online Booking Fee & Merchant Fee . Fees are applied once at checkout.'+tail
        s=Source('https://example.com','<html><body>'+t+'</body></html>',t)
        f=dict(fact_id='one',source_url=s.url,status='verified',verified_by='reviewer',verified_on='2026-09-13',claim=t,claim_type='price',value='505')
        return s,refined_structured(s,[f])
    def test_fields_and_qualifiers(self):
        s,o=self.build();fields=dict(o['notes']['offers'][0])
        self.assertEqual(fields['Departure'],'Brisbane (BNE)')
        self.assertEqual(fields['Starting fare stated on page'],'from $505')
        self.assertIn('exclude Online Booking Fee',fields['Fees'])
        self.assertNotIn('AUD',o['clean'])
        self.assertEqual(o['evidence'][0]['quote'],s.clean)
    def test_unknown_qualification_is_noop(self):
        s,o=self.build(' Only valid on Tuesdays.')
        self.assertEqual(o['clean'],s.clean)
        self.assertFalse(o['notes']['inserted'])
    def test_duplicate_retired(self):
        self.assertNotIn('verified_quantitative_facts',ACTIVE)
        self.assertIn('verified_quantitative_facts',RETIRED)

if __name__=='__main__':unittest.main()
