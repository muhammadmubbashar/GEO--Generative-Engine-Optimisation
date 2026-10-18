import unittest
from pathlib import Path
from .arms import Source,cleaned
from .remaining import load_external
from .external_refinement import refined_external

class ExternalPlacement(unittest.TestCase):
    def test_fee_notice_precedes_context(self):
        raw='<html><body><h1>Flights to Sydney</h1><p>Sydney (SYD) $99</p><div><span data-testid="AlertBody">Displayed fares exclude fees. Fees are applied once at checkout.</span></div></body></html>'
        s=Source('https://example.com',raw,cleaned(raw))
        o=refined_external(s,load_external(Path('results/remaining_methods_v3/external_source')))
        self.assertLess(o['clean'].index('Fees are applied once at checkout.'),o['clean'].index('Sydney Airport context'))
    def test_navigation_mention_only_noop(self):
        raw='<html><body><h1>Melbourne flights</h1><nav>Sydney Airport</nav></body></html>'
        s=Source('https://example.com',raw,'Melbourne flights Sydney Airport')
        o=refined_external(s,load_external(Path('results/remaining_methods_v3/external_source')))
        self.assertEqual(o['html'],raw)
        self.assertFalse(o['notes']['inserted'])

if __name__=='__main__':unittest.main()
