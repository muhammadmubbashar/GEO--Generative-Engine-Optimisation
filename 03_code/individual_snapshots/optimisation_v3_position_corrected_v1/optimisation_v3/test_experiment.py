"""Record integrity checks independent of live provider calls."""
import unittest,tempfile
from pathlib import Path
from optimisation_v3.experiment import checked_record,run
from geo_bench import baseline_v2 as b

class RecordChecks(unittest.TestCase):
    def fixture(self,out):
        job={'key':'rendered__Q01','query_id':'Q01','variant':'fixed','seed':1,'run':1,
             'arm':'rendered_content_exposure','pair_key':'Q01','path':'record.json'}
        queries={'Q01':{'query':'Travel information?'}}
        pool=[{'id':'1','brand':'flightcentre','file':'https://www.flightcentre.com.au/page',
               'text':'Frozen travel evidence.','words':3}]
        contexts={'rendered_content_exposure':{'Q01/fixed':pool}}
        lock={'experiment_id':'test','policy':{'fixed_chars':100}}
        prompt=b.planned_prompt(job,queries,contexts[job['arm']],lock)[-1]
        record={**job,'experiment_id':'test','prompt':prompt,'prompt_sha256':b.digest(prompt.encode()),
                'sources':[{'id':'1','brand':'flightcentre','url':pool[0]['file'],'text':pool[0]['text'],'original_chars':len(pool[0]['text'])}]}
        record['record_sha256']=b.digest(record);b.write(out/'record.json',record)
        return job,queries,contexts,lock,record
    def test_valid_record(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);j,q,c,l,r=self.fixture(out)
            self.assertEqual(checked_record(out,j,q,c,l),r)
    def test_rehashed_source_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);j,q,c,l,r=self.fixture(out);r['sources'][0]['text']='Invented evidence'
            r['record_sha256']=b.digest({k:v for k,v in r.items() if k!='record_sha256'});b.write(out/'record.json',r)
            with self.assertRaises(ValueError):checked_record(out,j,q,c,l)
    def test_rehashed_arm_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);j,q,c,l,r=self.fixture(out);r['arm']='baseline_repeat'
            r['record_sha256']=b.digest({k:v for k,v in r.items() if k!='record_sha256'});b.write(out/'record.json',r)
            with self.assertRaises(ValueError):checked_record(out,j,q,c,l)
    def test_superseded_generation_block(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'GENERATION_DEFERRED.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'deferred'):run(out,4)

if __name__=='__main__':unittest.main()
