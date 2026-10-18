"""Repaired research-only methods. No generation or implicit data access.

These implementations are not added to the rendered experiment schedule.
Padding remains retired; query repetition declares oracle information access.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime
from decimal import Decimal,ROUND_CEILING
import hashlib,html,json,re
from bs4 import BeautifulSoup
from .arms import Source,sha,cleaned,append_body,quoted,validate_output

RESEARCH_ONLY=('external_source_attribution','external_fact_only',
               'oracle_query_repetition','fare_plus_attribution')

def source_text(raw):
    soup=BeautifulSoup(raw,'html.parser')
    for tag in soup(['script','style','nav','footer','header']):tag.decompose()
    return ' '.join(soup.stripped_strings)

@dataclass(frozen=True)
class ExternalEvidence:
    source_url: str
    publisher: str
    raw_sha256: str
    text_sha256: str
    quote: str
    quote_start: int
    quote_end: int
    fetched_at: str
    review_method: str
    fact_period: str
    entity: str

def load_external(directory):
    """Validate the exact frozen primary-source quotation, without live fetching."""
    directory=Path(directory)
    meta=json.loads((directory/'meta.json').read_text(encoding='utf-8'))
    raw=(directory/'raw.html').read_bytes();text=(directory/'text.txt').read_text(encoding='utf-8')
    url=urlsplit(meta['source_url'])
    # This first repaired citation dataset is explicitly Sydney Airport only.
    if url.scheme!='https' or url.hostname!='www.sydneyairport.com.au' or url.username or url.password:
        raise ValueError('External source is not the declared primary publisher')
    if meta['source_url']!=meta['final_url'] or meta['status_code']!=200:raise ValueError('External URL/status mismatch')
    if hashlib.sha256(raw).hexdigest()!=meta['raw_sha256'] or sha(text)!=meta['text_sha256']:
        raise ValueError('External source bytes changed')
    if source_text(raw)!=text:raise ValueError('External text is not derived from captured HTML')
    start,end=meta['quote_start'],meta['quote_end'];quote=meta['quote']
    if not quote or len(quote.split())>25 or text[start:end]!=quote:raise ValueError('Unsupported external quotation')
    if not meta.get('review_method') or meta.get('publisher')!='Sydney Airport':raise ValueError('Missing or wrong publisher/source-check provenance')
    datetime.fromisoformat(meta['fetched_at'])
    if meta.get('fact_period')!='2025' or '2025' not in quote:raise ValueError('Fact period mismatch')
    return ExternalEvidence(meta['source_url'],meta['publisher'],meta['raw_sha256'],meta['text_sha256'],quote,start,end,
                            meta['fetched_at'],meta['review_method'],meta['fact_period'],'Sydney Airport (SYD)')

def entity_match(source):
    """Airport evidence, not an arbitrary city substring or airline abbreviation."""
    match=re.search(r'\bSydney\s+Airport\b|\bSydney\s*\(\s*SYD\s*\)',source.clean,re.I)
    return {'start':match.start(),'end':match.end(),'text':match.group()} if match else None

def attribution_block(source,external,with_attribution=True):
    match=entity_match(source)
    if not match:return '',[],None
    block='<section id="geo-v3-external"><blockquote>'+html.escape(external.quote)+'</blockquote>'
    if with_attribution:
        block+='<p>Source: <a href="'+html.escape(external.source_url,quote=True)+'">'+html.escape(external.publisher+' — '+external.source_url)+'</a></p>'
    block+='</section>'
    return block,[asdict(external)],match

def result(source,arm,raw,evidence,notes):
    text=cleaned(raw) if raw!=source.html else source.clean
    return {'arm':arm,'url':source.url,'html':raw,'clean':text,'source_sha256':sha(source.clean),
            'raw_sha256':sha(raw),'clean_sha256':sha(text),'evidence':evidence,
            'notes':{**notes,'uses_llm':False,'research_only':True}}

def attribution(source,external,with_attribution=True):
    block,ledger,match=attribution_block(source,external,with_attribution)
    arm='external_source_attribution' if with_attribution else 'external_fact_only'
    raw=append_body(source.html,block) if block else source.html
    return result(source,arm,raw,ledger,{'inserted':bool(block),'entity_evidence':match,
                  'unchanged_reason':'' if block else 'no_explicit_Sydney_Airport_or_SYD_evidence',
                  'review_scope':'exact primary-source quotation checked by assistant; human release review not claimed',
                  'estimand':'factual addition plus attribution' if with_attribution else 'same factual addition without attribution'})

def oracle_repetition(source,query_texts,rate='0.03'):
    rate=Decimal(str(rate))
    if not rate.is_finite() or rate<0 or rate>Decimal('.1'):raise ValueError('Stress dose must be between zero and 10%')
    words=' '.join(q.lower() for q in query_texts).split()
    target=int((rate*len(source.clean.split())).to_integral_value(rounding=ROUND_CEILING))
    added=' '.join(words[i%len(words)] for i in range(target)) if words else ''
    raw=append_body(source.html,'<p id="geo-v3-oracle">'+html.escape(added)+'</p>') if added else source.html
    o=result(source,'oracle_query_repetition',raw,[],{'information_access':'evaluation_queries; oracle stress test',
              'query_text_sha256':sha(json.dumps(query_texts,ensure_ascii=False)),'dose_rate':str(rate),
              'requested_extra_words':target,'actual_extra_words':len(added.split()),
              'unchanged_reason':'no_query_mapping_or_zero_dose' if not added else '',
              'negative_effect_assumed':False})
    if added and len(o['clean'].split())-len(source.clean.split())!=target:
        raise ValueError('Cleaner changed more than the declared repetition dose')
    return o

def combined(source,facts,external):
    # Both component eligibility decisions use the original frozen Source.
    fare=quoted(source,facts,'fare_clarification')
    citation=attribution(source,external)
    block,ledger,match=attribution_block(source,external)
    raw=append_body(fare['html'],block) if block else fare['html']
    return result(source,'fare_plus_attribution',raw,fare['evidence']+ledger,
                  {'component_clean_sha256':{'fare_clarification':fare['clean_sha256'],
                                            'external_source_attribution':citation['clean_sha256']},
                   'fare_inserted':fare['notes']['inserted'],'citation_inserted':bool(block),
                   'entity_evidence':match,'eligibility_source':'original frozen page',
                   'interpretation':'combined policy; no synergy claim without separate interaction experiment'})

def retired_padding(*args,**kwargs):
    raise ValueError('padding_control is retired: no neutral, per-treatment matched manipulation is defined')

def validate_research_output(source,output,facts,external_directory,query_texts):
    """Reload the independent source freeze, not the output's claim ledger."""
    arm=output.get('arm')
    if arm=='oracle_query_repetition':expected=oracle_repetition(source,query_texts)
    elif arm in ('external_source_attribution','external_fact_only'):
        expected=attribution(source,load_external(external_directory),arm=='external_source_attribution')
    elif arm=='fare_plus_attribution':expected=combined(source,facts,load_external(external_directory))
    else:raise ValueError('Unknown/deferred/retired research method')
    validate_output(output,expected)
