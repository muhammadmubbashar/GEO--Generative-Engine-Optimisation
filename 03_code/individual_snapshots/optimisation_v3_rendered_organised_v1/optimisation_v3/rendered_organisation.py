"""Exploratory DOM ordering refinement. No queries, scores, or live fetches.

Move intact offer sections after existing explanatory sections in recognised
Flight Centre page templates. All other templates preserve the semantic arm.
"""
from collections import Counter
import re
from bs4 import BeautifulSoup
from .arms import semantic_rendered, cleaned, sha

ARM = 'rendered_content_organised'
RULES = (
    ('mc-deals-section', 'mc-journey-section'),
    ('rtw-deals-section', 'rtw-journey-section'),
    ('cot-air-transportation-deals', 'cot-faqs-section'),
)

def repair_currency(text):
    return re.sub(r'(\$)\s*((?:\d\s*){2,})(?=\s*\*)',
                  lambda m:m.group(1)+re.sub(r'\s+','',m.group(2)),text)

def organise_rendered(source, raw, meta):
    original = semantic_rendered(source, raw, meta)
    soup = BeautifulSoup(original['html'], 'html.parser')
    movements=[]
    for offers_id, explanation_id in RULES:
        offers=soup.find_all(attrs={'data-testid':offers_id})
        explanations=soup.find_all(attrs={'data-testid':explanation_id})
        if not offers or not explanations:
            continue
        if len(offers)!=1 or len(explanations)!=1:
            raise ValueError('Ambiguous ordering anchors: '+offers_id)
        offers,explanation=offers[0],explanations[0]
        cards=offers.select('[data-sku]')
        if not cards:
            continue
        if offers in explanation.parents or explanation in offers.parents:
            raise ValueError('Nested offer/explanation anchors')
        main=offers.find_parent('main')
        if main is None or explanation.find_parent('main') is not main:
            raise ValueError('Ordering anchors do not share main content')
        nodes=list(main.descendants)
        if next(i for i,n in enumerate(nodes) if n is offers)>next(i for i,n in enumerate(nodes) if n is explanation):
            continue
        before=str(offers)
        card_evidence=[{'sku':c.get('data-sku'),'html_sha256':sha(str(c)),
                        'semantic_text':repair_currency(cleaned(str(c)))} for c in cards]
        explanation.insert_after(offers.extract())
        if str(offers)!=before:
            raise ValueError('Moving offers changed subtree')
        movements.append({'offers_anchor':offers_id,'after_anchor':explanation_id,
                          'subtree_sha256':sha(before),'cards':card_evidence})
    if not movements:
        return {**original,'arm':ARM,'notes':{**original['notes'],'ordering_refinement':True,
                'movements':[],'unchanged_reason':'no_applicable_move_in_recognised_template',
                'parent_semantic_sha256':original['clean_sha256']}}
    markup=str(soup);text=repair_currency(cleaned(markup))
    if Counter(text.split())!=Counter(original['clean'].split()):
        raise ValueError('Ordering changed cleaned token inventory')
    return {**original,'arm':ARM,'html':markup,'clean':text,'raw_sha256':sha(markup),
            'clean_sha256':sha(text),'evidence':original['evidence'],
            'notes':{**original['notes'],'ordering_refinement':True,'movements':movements,
            'parent_semantic_sha256':original['clean_sha256'],
            'interpretation':'dated rendered content plus currency repair and template-based section ordering; exploratory',
            'query_access':False,'rule_design':'exploratory; informed by earlier development observations'}}
