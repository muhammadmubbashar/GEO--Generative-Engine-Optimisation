"""Source-only FAQ refinement. No query, outcome, live-fetch or model input."""
import html
import re
from dataclasses import asdict
from urllib.parse import urlsplit
from .arms import evidence, validate_evidence, append_body, cleaned, sha

ARM='page_grounded_faq_refined'

def question_for(source, e):
    text=e.quote
    # Decline inherited UK scope on Australian-origin route templates.
    if urlsplit(source.url).path.startswith('/flights/au/') and re.search(r'\bUK\b|United Kingdom|British Summer|Greenwich Mean',text,re.I):
        return None,'geographical_scope_mismatch'
    if re.search(r'\byears in the business\b|\bpeace of mind\b',text,re.I):
        return None,'company_promotion'
    route=re.search(r'Flights from (.+?) to (.+?) from \$',text)
    if e.claim_type=='price' and route:
        origin,destination=route.groups()
        if len(origin)>90 or len(destination)>90:return None,'ambiguous_route'
        return f'What fare and fees does this page state for flights from {origin} to {destination}?',''
    if re.search(r'round the world fares are valid',text,re.I):
        return 'What ticket validity and date-change guidance does this page give for round-the-world travel?',''
    if 'Star Alliance' in text and 'Circle Pacific' in text:
        return 'What network, mileage and Circle Pacific details does this page describe for Star Alliance?',''
    if 'Star Alliance Asia Airpass' in text:
        return 'What destinations and flight-sector limits does this page describe for the Star Alliance Asia Airpass?',''
    if re.search(r'one direction',text,re.I) and 'point of origin' in text:
        return 'What direction, return-point and stop-count guidance does this page give for round-the-world tickets?',''
    return None,'no_supported_specific_question'

def refined_faq(source,facts):
    available=evidence(source,facts);accepted=[];rejected=[]
    for e in available:
        q,reason=question_for(source,e)
        if q:accepted.append((e,q))
        else:rejected.append({'fact_id':e.fact_id,'reason':reason})
    # Keep the largest intact evidence span; do not trim away its qualifiers.
    selected=[]
    for e,q in sorted(accepted,key=lambda x:(-(x[0].end-x[0].start),x[0].start,x[0].fact_id)):
        if any(e.start<s.end and s.start<e.end or e.quote in s.quote or s.quote in e.quote for s,_ in selected):
            rejected.append({'fact_id':e.fact_id,'reason':'overlapping_or_duplicate_span'});continue
        selected.append((e,q))
    selected.sort(key=lambda x:(x[0].start,x[0].fact_id))
    groups={}
    for e,q in selected:groups.setdefault(q,[]).append(e)
    raw=source.html
    if selected:
        section='<section id="geo-v3-faq-refined"><h2>Frequently asked questions</h2>'
        section+=''.join('<h3>'+html.escape(q)+'</h3>'+''.join('<blockquote>'+html.escape(e.quote)+'</blockquote>' for e in es) for q,es in groups.items())+'</section>'
        raw=append_body(raw,section)
    text=cleaned(raw) if selected else source.clean
    ledger=[asdict(e) for e,_ in selected];validate_evidence(source,ledger,facts)
    return {'arm':ARM,'url':source.url,'html':raw,'clean':text,'source_sha256':sha(source.clean),
            'raw_sha256':sha(raw),'clean_sha256':sha(text),'evidence':ledger,
            'notes':{'inserted':bool(selected),'questions':list(groups),'rejected':rejected,
                     'interpretation':'exploratory FAQ quotation packaging refinement; historical claims, not live verification',
                     'rules':'source-only specific questions; intact non-overlapping answers; no query access; original page retained'}}
