import unittest
from collections import Counter
from bs4 import BeautifulSoup
from optimisation_v3.arms import Source,sha,semantic_rendered
from optimisation_v3.rendered_organisation import organise_rendered

class OrganisationChecks(unittest.TestCase):
    def fixture(self, extra='', offers_id='mc-deals-section', explanation_id='mc-journey-section'):
        url='https://www.flightcentre.com.au/example'
        intro='Travel guidance about booking flights and planning your journey. '*18
        markup=f'<html><head><title>Travel</title><link rel="canonical" href="{url}"></head><body><main><p>Introduction</p><div data-testid="{offers_id}"><h2>Available offers</h2><a data-sku="123"><p>Brisbane to Sydney Qantas $ 2 1 9 * Economy One way</p><p>Available between: 10 Oct 26 - 15 Nov 26</p></a><p>Fares exclude booking fees.</p></div><div data-testid="{explanation_id}"><h2>Journey explanation</h2><p>{intro}</p></div>{extra}</main></body></html>'
        raw=markup.encode();return Source(url,markup,intro),raw,{'status':'ok','url':url,'sha256':sha(markup),'rendered_at':'2026-08-26'}

    def test_move_preserves_card_conditions_and_inventory(self):
        args=self.fixture();old=semantic_rendered(*args);new=organise_rendered(*args)
        self.assertLess(new['clean'].index('Journey explanation'),new['clean'].index('Available offers'))
        self.assertEqual(Counter(old['clean'].split()),Counter(new['clean'].split()))
        self.assertIn('Qantas $219*',new['clean'])
        old_card=BeautifulSoup(old['html'],'html.parser').select_one('[data-sku]')
        new_card=BeautifulSoup(new['html'],'html.parser').select_one('[data-sku]')
        self.assertEqual(str(old_card),str(new_card))
        self.assertIn('Fares exclude booking fees.',new['clean'])

    def test_unknown_template_exact_noop(self):
        args=self.fixture(offers_id='route-offers',explanation_id='route-info')
        before=semantic_rendered(*args);after=organise_rendered(*args)
        self.assertEqual(before['clean'],after['clean']);self.assertEqual(before['html'],after['html'])

    def test_ambiguous_template_rejected(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            organise_rendered(*self.fixture('<div data-testid="mc-journey-section">Another explanation</div>'))

    def test_already_ordered_is_noop(self):
        args=self.fixture();first=organise_rendered(*args);raw=first['html'].encode()
        second=organise_rendered(args[0],raw,{**args[2],'sha256':sha(first['html'])})
        self.assertEqual(first['clean'],second['clean']);self.assertEqual([],second['notes']['movements'])

if __name__=='__main__':unittest.main()
