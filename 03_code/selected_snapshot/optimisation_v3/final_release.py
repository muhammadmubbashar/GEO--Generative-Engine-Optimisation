"""Release 2026-09-20: explicit-input, same-snapshot content policies.

Historical builders remain available for reproducing old runs. No queries,
retrieval scores, live fetches or generation calls are used here.
"""
import html
import json
import re
from collections import Counter
from bs4 import BeautifulSoup
from .arms import Source, cleaned, sha, append_body
from .coherent_refinement import coherent_rendered, useful_external

RELEASE_ARMS = ('v3_rendered_final', 'v3_faq_final', 'v3_product_facts_final',
                'v3_external_attributed_final', 'v3_external_fact_only_final',
                'v3_schema_only_final', 'v3_selective_offers_final', 'v3_final_core')
PRICE = re.compile(r'^\$\s*[\d][\d,\s]*(?:\.\d{1,2})?\s*[*^]?$')
SPLIT = re.compile(r'\$\s*(?:\d\s+){1,}\d')
ROUTE = re.compile(r'^Cheap Flights from (.+?) \(([A-Z]{3})\) to (.+?) \(([A-Z]{3})\) from (\$[\d,]+(?:\.\d+)?)$')
FEE = 'Displayed fares exclude Online Booking Fee & Merchant Fee . Fees are applied once at checkout.'

def finish(source, arm, markup, evidence=(), **notes):
    text = cleaned(markup) if markup != source.html else source.clean
    return {'arm':arm,'url':source.url,'html':markup,'clean':text,
            'source_sha256':sha(source.clean),'raw_sha256':sha(markup),
            'clean_sha256':sha(text),'evidence':list(evidence),
            'notes':{'query_access':False,'inserted':text!=source.clean,**notes}}

def normalise_price_dom(markup):
    """Join only a complete currency element; keep the amount and qualifiers."""
    soup=BeautifulSoup(markup,'html.parser')
    before=cleaned(markup)
    for el in reversed(soup.find_all(['div','span','p','strong'])):
        if el.decomposed or not el.contents:continue
        value=el.get_text(' ',strip=True)
        if PRICE.fullmatch(value) and re.search(r'\s',value):
            # Do not delete route, date, cabin, fare conditions or card attributes.
            el.clear();el.append(re.sub(r'\s+','',value))
        elif SPLIT.search(value) and len(value)<160 and not el.find(['a','button','script','style']) and not any(SPLIT.search(c.get_text(' ',strip=True)) for c in el.find_all(recursive=False)):
            # Some templates share the lowest amount container with cabin text.
            # Preserve that entire short label, changing currency whitespace only.
            repaired=re.sub(r'(\$)\s*((?:\d\s*){2,})(?=\s*\*)',lambda m:m.group(1)+re.sub(r'\s+','',m.group(2)),value)
            if repaired!=value:el.clear();el.append(repaired)
    result=str(soup)
    # Only whitespace may change in the evaluated representation.
    if re.sub(r'\s','',before)!=re.sub(r'\s','',cleaned(result)):
        raise ValueError('Currency normalisation changed non-whitespace content')
    if SPLIT.search(cleaned(result)):
        raise ValueError('Unresolved currency DOM: needs explicit template review')
    return result

def rendered_final(source, raw, meta):
    r=coherent_rendered(source,raw,meta)
    markup=normalise_price_dom(r['html'])
    return finish(source,'v3_rendered_final',markup,
                  [{'kind':'capture','source_url':source.url,'capture_sha256':meta['sha256'],
                    'captured_at':meta['rendered_at'],'normalisation':'currency whitespace only'}],
                  capture_sha256=meta['sha256'],captured_at=meta['rendered_at'],
                  movements=r['notes']['movements'],
                  interpretation='dated rendered replacement plus semantic organisation; not pure SSR')

def route_record(source):
    """Typed, bounded template, sourced from this exact HTML/text snapshot."""
    if cleaned(source.html)!=source.clean:raise ValueError('Source HTML/text snapshot mismatch')
    soup=BeautifulSoup(source.html,'html.parser')
    headings=soup.find_all('h1')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    m=ROUTE.fullmatch(title)
    if not m or len(headings)!=1 or FEE not in source.clean:return None
    origin,oc,destination,dc,price=m.groups()
    h=headings[0].get_text(' ',strip=True)
    if h!=f'Flights from {origin} to {destination} {price} ^':return None
    if title not in source.clean:return None
    spans=[]
    for quote in (title,FEE):
        start=source.clean.index(quote)
        spans.append({'start':start,'end':start+len(quote),'quote':quote})
    return {'fact_id':sha(source.url+'|'+sha(source.clean)+'|route')[:20],
            'source_url':source.url,'source_sha256':sha(source.clean),
            'origin':origin,'origin_code':oc,'destination':destination,'destination_code':dc,
            'starting_fare':price,'currency_code':None,'fees':FEE,'spans':spans,
            'scope':'historical starting fare; no journey type, dates or currency code inferred'}

def validate_fact(source, record):
    if record!=route_record(source):raise ValueError('Fact not grounded in current snapshot')

def _fields(r, include_fees=True):
    rows=[('Departure',r['origin']+' ('+r['origin_code']+')'),
          ('Destination',r['destination']+' ('+r['destination_code']+')'),
          ('Starting fare stated on page','from '+r['starting_fare'])]
    if include_fees:rows.append(('Fees',r['fees']))
    return '<dl>'+''.join('<dt>'+html.escape(k)+'</dt><dd>'+html.escape(v)+'</dd>' for k,v in rows)+'</dl>'

def package_route(source, mode, arm=None):
    r=route_record(source);arm=arm or ('v3_faq_final' if mode=='faq' else 'v3_product_facts_final')
    if not r:return finish(source,arm,source.html,reason='unsupported_or_inconsistent_route_template')
    validate_fact(source,r)
    q='What starting fare and fees does this page state for '+r['origin']+' to '+r['destination']+'?'
    if mode=='faq':
        answer='Flights from '+r['origin']+' ('+r['origin_code']+') to '+r['destination']+' ('+r['destination_code']+') from '+r['starting_fare']+'. '+r['fees']
        block='<h2>'+html.escape(q)+'</h2><p>'+html.escape(answer)+'</p>'
    elif mode=='facts':block='<h2>Route and fare details</h2>'+_fields(r)
    elif mode=='joint':block='<h2>'+html.escape(q)+'</h2>'+_fields(r)
    else:raise ValueError('Unknown packaging policy')
    section='<section id="geo-final-route">'+block+'</section>'
    # Place after the full fee paragraph, not after the footer or within a price.
    soup=BeautifulSoup(source.html,'html.parser')
    if soup.find(id='geo-final-route'):raise ValueError('Already packaged')
    anchors=[p for p in soup.find_all(['p','span','div']) if p.get_text(' ',strip=True)==FEE]
    # Raw and rendered templates use different tags and nested wrappers.
    # Choose the outermost exact fee-only container; never split the clause.
    anchors=[p for p in anchors if not any(a.get_text(' ',strip=True)==FEE for a in p.parents if a.name not in ('html','body','main','[document]'))]
    if len(anchors)!=1:return finish(source,arm,source.html,reason='ambiguous_fee_anchor')
    node=BeautifulSoup(section,'html.parser').section
    if mode=='joint':
        # The joint section already contains the exact fee clause. Replace only
        # its fee-only container so the final stack does not repeat that clause.
        fee_container=anchors[0]
        fee_container.replace_with(node)
        fee_field=node.find_all('dd')[-1]
        fee_field.clear()
        fee_field.append(fee_container)  # retain original condition links/markup
    else:
        anchors[0].insert_after(node)
    return finish(source,arm,str(soup),[r],packaging=mode,
                  interpretation='same-snapshot evidence packaging; repeated source information, not pure format-only')

def schema_only(source):
    r=route_record(source)
    if not r:return finish(source,'v3_schema_only_final',source.html,reason='no_grounded_route_record')
    name='Flights from '+r['origin']+' ('+r['origin_code']+') to '+r['destination']+' ('+r['destination_code']+')'
    # A lower-bound PriceSpecification, not an unconditional all-in/live price.
    offer={'@type':'Offer','@id':source.url+'#geo-final-offer','url':source.url,
           'name':name,'description':'Starting fare stated on page: from '+r['starting_fare']+'. '+r['fees'],
           'itemOffered':{'@type':'Service','name':name},
           'priceSpecification':{'@type':'PriceSpecification','minPrice':r['starting_fare'][1:].replace(',',''),'description':r['fees']}}
    payload={'@context':'https://schema.org','@graph':[
        {'@type':'WebPage','@id':source.url+'#geo-final-page','url':source.url,'name':name,'mainEntity':{'@id':offer['@id']}},offer]}
    block='<script id="geo-final-schema" type="application/ld+json">'+json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')+'</script>'
    if 'geo-final-schema' in source.html:raise ValueError('Already marked up')
    i=source.html.lower().rfind('</head>')
    if i<0:return finish(source,'v3_schema_only_final',source.html,reason='missing_head')
    markup=source.html[:i]+block+source.html[i:]
    from geo_bench.retrieval.cleaner import clean_html
    if clean_html(markup)[0]!=clean_html(source.html)[0]:raise ValueError('Schema changed visible body')
    return finish(source,'v3_schema_only_final',markup,[r],
                  interpretation='JSON-LD serialization consumed as text by unchanged lab engine; body identical; not graph-aware ranking',
                  currency_code_omitted=True,rich_result_eligibility_claimed=False)

def external_final(source,evidence,attributed=True):
    if not evidence.get('quote') or not evidence.get('raw_sha256'):raise ValueError('Missing frozen external evidence')
    r=useful_external(source,evidence)
    arm='v3_external_attributed_final' if attributed else 'v3_external_fact_only_final'
    markup=r['html']
    if r['notes'].get('inserted') and not attributed:
        soup=BeautifulSoup(markup,'html.parser');section=soup.find(id='geo-external-useful')
        # Remove attribution only. Keep the exact same fact, placement and caveat.
        link=section.find('a');link.extract()
        p=section.find_all('p')[-1]
        p.string='Airport access information; ground transport is separate from the airfare. Check the operator for current services.'
        markup=str(soup)
    return finish(source,arm,markup,r['evidence'],**{k:v for k,v in r['notes'].items() if k not in ('inserted','query_access')},
                  attribution_included=attributed)

def selective_offers(source,raw,meta):
    full=rendered_final(source,raw,meta)
    s=Source(source.url,full['html'],full['clean']);record=route_record(s)
    if not record:return finish(source,'v3_selective_offers_final',source.html,reason='no_exact_route_scope')
    soup=BeautifulSoup(full['html'],'html.parser');selected=[];seen=set()
    for card in soup.select('[data-sku]'):
        text=cleaned(str(card))
        required=(record['origin']+' ('+record['origin_code']+')',record['destination']+' ('+record['destination_code']+')')
        if not all(x in text for x in required):continue
        if not re.search(r'\$\d',text) or 'Available between:' not in text:continue
        if text in source.clean or text in seen:continue
        seen.add(text);selected.append({'sku':card['data-sku'],'quote':text,'card_sha256':sha(str(card))})
        if len(selected)==2:break
    if not selected:return finish(source,'v3_selective_offers_final',source.html,reason='no_complete_matching_new_cards')
    date=meta['rendered_at'][:10]
    block='<section id="geo-final-selective"><h2>Separate captured offer cards — '+html.escape(date)+'</h2><p>These historical cards come from a later capture than the original page headline.</p>'
    block+=''.join('<p>'+html.escape(x['quote'])+'</p>' for x in selected)+'<p>'+html.escape(record['fees'])+'</p></section>'
    return finish(source,'v3_selective_offers_final',append_body(source.html,block),
                  [{'source_url':source.url,'capture_sha256':meta['sha256'],'captured_at':meta['rendered_at'],**x} for x in selected],
                  interpretation='complete route-matched dated cards, not updated headline fares; excluded from core stack')

def final_core(source,raw,meta):
    rendered=rendered_final(source,raw,meta)
    return combine_rendered(source,rendered)

def combine_rendered(source,rendered):
    if (rendered['url']!=source.url or rendered['arm']!='v3_rendered_final'
            or rendered['source_sha256']!=sha(source.clean)
            or rendered['raw_sha256']!=sha(rendered['html'])
            or rendered['clean_sha256']!=sha(rendered['clean'])
            or cleaned(rendered['html'])!=rendered['clean']):
        raise ValueError('Rendered snapshot mismatch')
    canonical=Source(source.url,rendered['html'],rendered['clean'])
    joint=package_route(canonical,'joint','v3_final_core')
    components=[{'arm':'v3_rendered_final','status':'applied','output_sha256':rendered['clean_sha256']}]
    components.append({'arm':'faq_and_typed_facts_joint','status':'applied' if joint['notes']['inserted'] else 'noop',
                       'reason':joint['notes'].get('reason','')})
    out=finish(source,'v3_final_core',joint['html'],rendered['evidence']+joint['evidence'],
               components=components,canonical_source_sha256=canonical and sha(canonical.clean),
               interpretation='rendered semantic content plus one joint FAQ/typed-fact section; all facts from rendered snapshot',
               omitted=['schema','external','position','oracle','automatic_rewrite','selective_offers'],
               exploratory=True)
    if cleaned(out['html'])!=out['clean'] or SPLIT.search(out['clean']):raise ValueError('Final extraction invariant')
    return out

def validate_rewrite_release(source,output,review):
    """Mandatory factual-release gate; no claim to prove semantics automatically."""
    from scripts.rewrite_release_checks import validate_record,require_review
    validate_record(output,source.clean)
    require_review(source.clean,output['clean'],review)
    return {**output,'arm':'generic_rewrite_independently_reviewed',
            'notes':{**output.get('notes',{}),'not_autogeo_replication':True,'review':review}}
