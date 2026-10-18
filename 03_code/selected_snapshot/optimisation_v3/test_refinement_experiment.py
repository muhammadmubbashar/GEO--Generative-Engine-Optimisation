import unittest
from collections import Counter
from .refinement_experiment import ARMS,ARM,schedule_triplets,comparison


class RefinementExperimentTests(unittest.TestCase):
    def test_triplets_cover_every_arm_preserve_job_and_balance_order(self):
        original=[{'key':f'Q{i}_fixed_s1_r1','query_id':f'Q{i}','variant':'fixed','seed':1,'run':1} for i in range(12)]
        jobs=schedule_triplets(original)
        self.assertEqual(jobs,schedule_triplets(original))
        self.assertEqual(len({j['path'] for j in jobs}),36)
        orders=[]
        for i in range(0,len(jobs),3):
            triplet=jobs[i:i+3]
            self.assertEqual({j['arm'] for j in triplet},set(ARMS))
            self.assertEqual(len({j['pair_key'] for j in triplet}),1)
            self.assertTrue(all(j['variant']=='fixed' and j['seed']==1 and j['run']==1 for j in triplet))
            orders.append(tuple(j['arm'] for j in triplet))
        self.assertEqual(sorted(Counter(orders).values()),[2]*6)

    def test_incremental_comparison_uses_r4_not_baseline(self):
        rows=[]
        for i in range(2):
            for arm,v in [('baseline_repeat',0),('v3_final_core',1),(ARM,0)]:
                rows.append({'pair_key':str(i),'query_id':f'Q{i}','arm':arm,
                             'citation_inclusion':v,'citation_share':v,'retrieval_inclusion':v})
        self.assertEqual(comparison(rows,ARM,'baseline_repeat')['citation_inclusion']['difference'],0)
        self.assertEqual(comparison(rows,ARM,'v3_final_core')['citation_inclusion']['difference'],-1)
        self.assertEqual(comparison(rows,'v3_final_core','baseline_repeat')['citation_inclusion']['difference'],1)
        self.assertIsNone(comparison(rows[:-1],ARM,'v3_final_core'))


if __name__=='__main__':unittest.main()
