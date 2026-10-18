import unittest,json
from bs4 import BeautifulSoup
from .arms import Source,cleaned,sha
from .final_release import *
from geo_bench.retrieval.cleaner import clean_html

def fixture(price='99',extra=''):
    url='https://www.flightcentre.com.au/flights/au-vic-melbourne/au-nsw-sydney'
    title='Cheap Flights from Melbourne (MEL) to Sydney (SYD) from $'+price
    raw='<html><head><title>'+title+'</title><link rel="canonical" href="'+url+'"></head><body><main><h1>Flights from Melbourne to Sydney $'+price+' <sup>^</sup></h1><p data-testid="AlertBody">'+FEE+'</p><p>'+('Plan your journey with complete airline conditions. '*25)+'</p>'+extra+'</main></body></html>'
    return Source(url,raw,cleaned(raw))

class FinalReleaseChecks(unittest.TestCase):
    def test_nested_span_fee_anchor_used_in_raw_snapshot(self):
        s=fixture();raw=s.html.replace('<p data-testid="AlertBody">'+FEE+'</p>','<div><div><span>'+FEE+'</span></div></div>')
        out=package_route(Source(s.url,raw,cleaned(raw)),'faq')
        self.assertTrue(out['notes']['inserted'])
        self.assertEqual(len(BeautifulSoup(out['html'],'html.parser').select('#geo-final-route')),1)

    def test_joint_keeps_original_fee_links_once(self):
        s=fixture()
        raw=s.html.replace('Online Booking Fee','<a href="https://example.com/fee">Online Booking Fee</a>')
        s=Source(s.url,raw,cleaned(raw))
        out=package_route(s,'joint')
        soup=BeautifulSoup(out['html'],'html.parser')
        self.assertEqual(out['clean'].count(FEE),1)
        self.assertEqual(soup.select_one('#geo-final-route a')['href'],'https://example.com/fee')

    def test_two_digit_price_with_cabin_is_repaired(self):
        raw='<div><span>$</span><span>8</span><span>8</span><span>*</span><span>Economy, One way</span></div>'
        out=normalise_price_dom(raw)
        self.assertIn('$88*',cleaned(out))
        self.assertIn('Economy, One way',cleaned(out))
        self.assertFalse(SPLIT.search(cleaned(out)))

    def test_composer_rejects_wrong_page_and_hash(self):
        s=fixture()
        r=finish(s,'v3_rendered_final',s.html)
        for field,value in [('url','https://example.com/other'),('raw_sha256','bad'),('clean_sha256','bad')]:
            with self.assertRaisesRegex(ValueError,'snapshot'):
                combine_rendered(s,{**r,field:value})
    def test_composer_uses_new_capture_not_old_fare(self):
        old,new=fixture(),fixture('89')
        out=final_core(old,new.html.encode(),{'status':'ok','url':old.url,'sha256':sha(new.html),'rendered_at':'2026-08-26'})
        self.assertNotIn('$99',out['clean']);self.assertIn('$89',out['clean'])
        self.assertEqual(out['clean'].count(FEE),new.clean.count(FEE))
        self.assertEqual(cleaned(out['html']),out['clean'])
        self.assertEqual(out['evidence'][-1]['source_sha256'],out['notes']['canonical_source_sha256'])
        self.assertEqual(len(BeautifulSoup(out['html'],'html.parser').select('#geo-final-route')),1)

    def test_price_repair_persists_through_html_extraction(self):
        raw='<html><body><div><span>$</span><span>2</span><span>1</span><span>9</span><span>*</span><span>Economy, One way</span></div><p>Available between: 10 Oct 26 - 15 Nov 26</p></body></html>'
        out=normalise_price_dom(raw)
        self.assertIn('$219*',cleaned(out));self.assertIn('Economy, One way',cleaned(out))
        self.assertIn('10 Oct 26 - 15 Nov 26',cleaned(out))
        self.assertEqual(cleaned(normalise_price_dom(out)),cleaned(out))

    def test_schema_is_metadata_only_and_scoped(self):
        s=fixture();out=schema_only(s)
        self.assertEqual(clean_html(s.html)[0],clean_html(out['html'])[0])
        node=BeautifulSoup(out['html'],'html.parser').find(id='geo-final-schema')
        offer=json.loads(node.string)['@graph'][1]
        self.assertIn('Melbourne',offer['name']);self.assertIn('Sydney',offer['name'])
        self.assertEqual(offer['priceSpecification']['minPrice'],'99')
        self.assertNotIn('priceCurrency',offer['priceSpecification'])
        self.assertIn('exclude',offer['description'])

    def test_reject_inconsistent_source_and_promotional_nonproduct(self):
        s=fixture();bad=Source(s.url,s.html,s.clean.replace('$99','$89'))
        with self.assertRaisesRegex(ValueError,'snapshot'):route_record(bad)
        raw='<html><body><h1>Our company</h1><p>40 years in the business</p></body></html>'
        o=package_route(Source(s.url,raw,cleaned(raw)),'facts')
        self.assertFalse(o['notes']['inserted'])

    def test_selective_requires_complete_matching_card(self):
        card='<a data-sku="one">Melbourne (MEL) to Sydney (SYD) Qantas $219* Economy One way Available between: 10 Oct 26 - 15 Nov 26</a>'
        old,new=fixture(),fixture('89',card)
        meta={'status':'ok','url':old.url,'sha256':sha(new.html),'rendered_at':'2026-08-26'}
        o=selective_offers(old,new.html.encode(),meta)
        self.assertIn('later capture',o['clean']);self.assertIn('15 Nov 26',o['clean'])
        self.assertEqual(len(o['evidence']),1)
        wrong=fixture('89',card.replace('Sydney (SYD)','Perth (PER)'))
        o=selective_offers(old,wrong.html.encode(),{**meta,'sha256':sha(wrong.html)})
        self.assertFalse(o['notes']['inserted'])

if __name__=='__main__':unittest.main()
