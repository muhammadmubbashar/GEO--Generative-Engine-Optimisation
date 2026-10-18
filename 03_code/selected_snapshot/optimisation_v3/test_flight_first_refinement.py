import unittest
from bs4 import BeautifulSoup
from .arms import Source
from .final_release import finish
from .flight_first_refinement import refine, ARM


def fixture(expanded='true', question='Which airport?', answer='Hobart Airport (HBA).'):
    raw='<html><head><title>Flights to Hobart</title><script type="application/ld+json">{"name":"Hobart"}</script></head><body><main><h1>Flights to Hobart</h1><div><h2>Explore Hobart</h2><p>Hotel information preserved.</p></div><div><div data-testid="AccordionTabsContainer"><h2>Frequently asked questions</h2><div data-testid="Accordion"><h3><button data-testid="AccordionTitle" aria-expanded="'+expanded+'">'+question+'</button></h3><div data-testid="AccordionContent">'+answer+' <a href="https://example.com/conditions">Conditions</a></div></div></div></div><button>Book now</button><div data-sku="fare">$192* Economy One way</div></main></body></html>'
    return finish(Source('https://www.flightcentre.com.au/flights/au/au-tas-hobart',raw,''),'v3_final_core',raw+' ')


class FlightFirstTests(unittest.TestCase):
    def test_restore_pair_move_whole_section_keep_conditions(self):
        old=fixture();new=refine(old)
        self.assertEqual(new['arm'],ARM)
        self.assertIn('Which airport? Hobart Airport (HBA). Conditions',new['clean'])
        self.assertLess(new['clean'].index('Frequently asked questions'),new['clean'].index('Explore Hobart'))
        self.assertNotIn('Book now',new['clean'])
        self.assertIn('$192* Economy One way',new['clean'])
        self.assertEqual(new['notes']['r5']['restored_questions'],1)
        self.assertEqual(len(BeautifulSoup(new['html'],'html.parser').select('a')),1)

    def test_closed_and_navigation_controls_not_converted(self):
        self.assertEqual(refine(fixture(expanded='false'))['notes']['r5']['restored_questions'],0)
        self.assertEqual(refine(fixture(question='Other flights'))['notes']['r5']['restored_questions'],0)

    def test_source_whitespace_matches_common_cleaner(self):
        out=refine(fixture(question='Which airport in  Hobart?'))
        self.assertIn('Which airport in Hobart? Hobart Airport',out['clean'])

    def test_reject_tampered_inputs_and_missing_answer(self):
        old=fixture()
        with self.assertRaises(ValueError):refine({**old,'clean':'tampered'})
        raw=old['html'].replace('data-testid="AccordionContent"','data-testid="Unknown"')
        from .arms import cleaned,sha
        new=refine({**old,'html':raw,'clean':cleaned(raw),'raw_sha256':sha(raw),'clean_sha256':sha(cleaned(raw))})
        self.assertEqual(new['notes']['r5']['restored_questions'],0)


if __name__=='__main__':unittest.main()
