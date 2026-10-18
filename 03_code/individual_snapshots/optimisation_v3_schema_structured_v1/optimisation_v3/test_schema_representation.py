import json
import unittest
from bs4 import BeautifulSoup
from .arms import Source,cleaned
from .schema_representation import schema_identity,objects

URL='https://www.flightcentre.com.au/example'
def source(graph='',heading='Flights from Sydney to Melbourne $99 ^'):
    raw='<html><head><link rel="canonical" href="'+URL+'">'+graph+'</head><body><h1>'+heading+'</h1><p>Displayed fares exclude fees. Conditions apply.</p></body></html>'
    return Source(URL,raw,cleaned(raw))
class SchemaTests(unittest.TestCase):
    def test_no_offer_or_price_inferred(self):
        s=source();out=schema_identity(s)
        self.assertEqual(out['notes']['fields']['name'],'Flights from Sydney to Melbourne')
        self.assertNotIn('price',out['notes']['fields'])
        self.assertEqual(BeautifulSoup(s.html,'html.parser').body,BeautifulSoup(out['html'],'html.parser').body)
    def test_preserves_existing_graph_and_only_adds_missing_fields(self):
        obj={'@context':'https://schema.org','@type':'FAQPage','mainEntity':[{'@type':'Question','name':'Conditions?','acceptedAnswer':{'@type':'Answer','text':'Not refundable.'}}]}
        script='<script type="application/ld+json">'+json.dumps(obj)+'</script>'
        out=schema_identity(source(script));new=json.loads(BeautifulSoup(out['html'],'html.parser').script.string)
        for k,v in obj.items():self.assertEqual(new[k],v)
        self.assertEqual(set(new)-set(obj),{'@id','url','name'})
        self.assertIn('Not refundable.',out['clean'])
    def test_conflict_and_malformed_noop(self):
        for graph in ['{bad','{"@type":"WebPage","url":"https://elsewhere.example/"}']:
            s=source('<script type="application/ld+json">'+graph+'</script>')
            self.assertEqual(schema_identity(s)['html'],s.html)
    def test_repeat_is_noop(self):
        o=schema_identity(source());s=Source(URL,o['html'],o['clean'])
        self.assertEqual(schema_identity(s)['html'],s.html)
    def test_strings_are_not_graph_nodes(self):
        raw=json.dumps({'description':'{"@type":"WebPage"}','@type':'Thing'})
        self.assertEqual(len(list(objects(raw))),1)
    def test_hidden_heading_noop(self):
        s=source();raw=s.html.replace('<h1>','<h1 hidden>');s=Source(URL,raw,cleaned(raw))
        self.assertFalse(schema_identity(s)['notes']['inserted'])
    def test_captured_url_used_when_canonical_absent_but_conflict_rejected(self):
        s=source();raw=s.html.replace('<link rel="canonical" href="'+URL+'">','')
        out=schema_identity(Source(URL,raw,cleaned(raw)))
        self.assertEqual(out['notes']['fields']['url'],URL)
        raw=s.html.replace('href="'+URL+'"','href="https://different.example/"')
        self.assertFalse(schema_identity(Source(URL,raw,cleaned(raw)))['notes']['inserted'])
if __name__=='__main__':unittest.main()
