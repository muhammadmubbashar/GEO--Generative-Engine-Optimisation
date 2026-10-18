"""Conservative route offer fields from intact, frozen source evidence."""
import re
import html
from dataclasses import asdict
from .arms import evidence, validate_evidence, append_body, cleaned, sha

ARM='structured_product_facts_refined'

def refined_structured(source,facts):
    offers=[];used=[];rejected=[];seen=set()
    for e in evidence(source,facts):
        m=re.match(r'Cheap Flights from (?P<origin>[^()]+) \((?P<origin_code>[A-Z]{3})\) to (?P<destination>[^()]+) \((?P<destination_code>[A-Z]{3})\) from (?P<fare>\$[\d,]+(?:\.\d+)?)\s',e.quote)
        if e.claim_type!='price' or not m:
            rejected.append({'fact_id':e.fact_id,'reason':'no_unambiguous_route_offer'});continue
        fee=re.search(r'Displayed fares exclude Online Booking Fee & Merchant Fee\s*\. Fees are applied once at checkout\.',e.quote)
        # Restrict this version to the known complete route/fee template.
        # Unknown qualifications are never silently discarded.
        if not fee or fee.end()!=len(e.quote):
            rejected.append({'fact_id':e.fact_id,'reason':'unrecognised_or_incomplete_qualifications'});continue
        middle=e.quote[m.end():fee.start()]
        if not re.fullmatch(r'Flights from '+re.escape(m['origin'])+r' to '+re.escape(m['destination'])+r' '+re.escape(m['fare'])+r' \^ Hot deals for a .+? getaway! ',middle):
            rejected.append({'fact_id':e.fact_id,'reason':'ambiguous_offer_template'});continue
        fields=[('Departure',m['origin']+' ('+m['origin_code']+')'),('Destination',m['destination']+' ('+m['destination_code']+')'),('Starting fare stated on page','from '+m['fare']),('Fees',fee.group())]
        identity=tuple(fields)
        if identity in seen:continue
        seen.add(identity);offers.append([list(field) for field in fields]);used.append(e)
    raw=source.html
    if offers:
        section='<section id="geo-v3-structured-refined"><h2>Product facts</h2>'
        section+=''.join('<dl>'+''.join('<dt>'+html.escape(k)+'</dt><dd>'+html.escape(v)+'</dd>' for k,v in fields)+'</dl>' for fields in offers)+'</section>'
        raw=append_body(raw,section)
    text=cleaned(raw) if offers else source.clean
    ledger=[asdict(e) for e in used];validate_evidence(source,ledger,facts)
    return {'arm':ARM,'url':source.url,'html':raw,'clean':text,'source_sha256':sha(source.clean),'raw_sha256':sha(raw),'clean_sha256':sha(text),'evidence':ledger,
            'notes':{'offers':offers,'rejected':rejected,'inserted':bool(offers),'interpretation':'exploratory attribute-value packaging; historical starting fare; currency code, dates and journey type not inferred; unsupported templates unchanged'}}

def route_structured(source,facts):
    """One explicit route relation per offer; preserve v1 fields and eligibility."""
    out=refined_structured(source,facts)
    routes=['Flights from '+dict(fields)['Departure']+' to '+dict(fields)['Destination']+'.' for fields in out['notes']['offers']]
    raw=out['html']
    if routes:
        start=raw.index('<section id="geo-v3-structured-refined">')
        prefix,section=raw[:start],raw[start:]
        for route in routes:
            section=section.replace('<dl>','<p>'+html.escape(route)+'</p><dl data-route-added="true">',1)
        raw=prefix+section
    text=cleaned(raw) if routes else out['clean']
    return {**out,'arm':'structured_product_facts_route','html':raw,'clean':text,'raw_sha256':sha(raw),'clean_sha256':sha(text),
            'notes':{**out['notes'],'route_statements':routes,'refinement':'one explicit source-backed route statement; fields and eligibility unchanged; exploratory'}}
