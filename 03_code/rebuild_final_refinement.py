"""Rebuild the final FAQ stage from frozen prior-core inputs. No paid APIs.
This does not reconstruct the original web crawl or all earlier transformation stages.
Install the dependencies used by the selected snapshot before running (see README).
"""
from pathlib import Path
import sys, json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent/'selected_snapshot'))
from optimisation_v3.flight_first_refinement import refine
prior=json.loads((ROOT/'04_evidence/pages/prior_core.json').read_text(encoding='utf-8'))
expected=json.loads((ROOT/'04_evidence/pages/outputs.json').read_text(encoding='utf-8'))
count=0
for url,p in prior.items():
    rebuilt=refine(p)
    assert rebuilt['raw_sha256']==expected[url]['raw_sha256'],url
    assert rebuilt['clean_sha256']==expected[url]['clean_sha256'],url
    count+=1
result={'status':'PASS','pages':count,'scope':'Exact final FAQ refinement from supplied frozen prior-core inputs','html_and_clean_text_hashes':'All match selected saved outputs'}
(ROOT/'02_documentation/Refinement_Rebuild.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
