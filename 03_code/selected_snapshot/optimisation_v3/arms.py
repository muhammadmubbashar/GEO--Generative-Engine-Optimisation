"""Explicit-input deterministic interventions with exact source evidence.

No active-run lookup, live fetch, query access or self-attested claim ledger.
"""
from __future__ import annotations
import hashlib
import html
import re
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
from bs4 import BeautifulSoup
from geo_bench.retrieval.cleaner import clean_html
from geo_bench.search.live_retriever import normalise_url

ACTIVE = ('rendered_content_coherent_v2', 'external_source_useful_v3', 'schema_page_identity', 'rendered_content_exposure', 'page_grounded_faq', 'fare_clarification',
          'structured_product_facts',
          'rendered_content_semantic','autogeo_rewrite_exploratory',
          'external_source_attribution','position_control','full_stack_exploratory',
          'rendered_content_organised','page_grounded_faq_refined','structured_product_facts_refined','structured_product_facts_route','external_source_attribution_refined',
          'oracle_query_repetition','rendered_content_selective','schema_structured_markup','external_fact_only')
EXPLORATORY = ('autogeo_rewrite_exploratory',)
DEFERRED = {'schema_markup':'new markup is not consumed by this baseline',
            'freshness_signal':'crawl timestamp is not supplier verification'}
RETIRED = ('ssr_visible_digitfix','ssr_visible_twin','faq_structure',
           'statistics_addition_twin','padding_control','verified_quantitative_facts')
MONEY = re.compile(r'(?<![\w.])\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)(?!\d|[.,]\d)')

def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def cleaned(raw):
    body, graph = clean_html(raw)
    return (body+' '+graph).strip()

@dataclass(frozen=True)
class Source:
    url: str
    html: str
    clean: str

@dataclass(frozen=True)
class Evidence:
    fact_id: str
    source_url: str
    source_sha256: str
    start: int
    end: int
    quote: str
    value: str
    claim_type: str
    unit: str

def evidence(source, facts):
    """Expand verified source substrings to whole sentences, including next sentence.

    This deliberately declines unsupported/truncated/unlocatable facts. The next
    sentence retains adjacent fee qualifiers on the frozen route pages. This is
    source quotation, never a claim that every historical price is current.
    """
    ids=[f.get('fact_id') for f in facts]
    if any(not x for x in ids) or len(set(ids))!=len(ids):raise ValueError('Fact IDs must be present and unique')
    out=[]
    for f in sorted(facts, key=lambda x:x['fact_id']):
        if (f.get('status')!='verified' or f.get('source_url')!=source.url or
            not f.get('verified_by') or not f.get('verified_on')): continue
        claim=f.get('claim','').strip()
        pos=source.clean.find(claim)
        if len(claim)<20 or pos<0: continue
        boundaries=[0]+[m.end() for m in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])',source.clean)]+[len(source.clean)]
        start=max(b for b in boundaries if b<=pos)
        endings=[b for b in boundaries if b>=pos+len(claim)]
        end=endings[min(1,len(endings)-1)]
        quote=source.clean[start:end].strip()
        end=start+len(quote)
        if not quote or len(quote)>1600: continue
        e=Evidence(f['fact_id'],source.url,sha(source.clean),start,end,quote,f.get('value',''),f.get('claim_type',''),f.get('unit',''))
        if e.quote!=source.clean[e.start:e.end]: raise ValueError('Evidence offsets do not match')
        out.append(e)
    return out

def validate_evidence(source, ledger, facts):
    permitted={x.fact_id:asdict(x) for x in evidence(source,facts)}
    for e in ledger:
        if e.get('fact_id') not in permitted or e!=permitted[e['fact_id']]:
            raise ValueError('Claim has no exact, verified, page-specific evidence')

def append_body(raw, section):
    i=raw.lower().rfind('</body>')
    if i<0: raise ValueError('No body insertion point')
    return raw[:i]+section+raw[i:]

def fare_node(soup, value, currency='AUD', quoted_context=None):
    try: target=Decimal(value.replace(',',''))
    except InvalidOperation: return None
    if not soup.body: return None
    for node in soup.body.find_all(string=True):
        ancestors=list(node.parents)
        if any(a.name in {'script','style','noscript','template','head','nav','header','footer','aside'} or
               a.has_attr('hidden') or a.get('aria-hidden')=='true' or
               re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',a.get('style',''),re.I)
               for a in ancestors): continue
        # Require a local fare statement, not the coincidental same number in a fee.
        parent=node.parent
        local=parent.get_text(' ',strip=True)
        if len(local)>1600 or not re.search(r'\b(fares?|flights?)\b',local,re.I): continue
        if quoted_context is not None and local not in quoted_context:continue
        for m in MONEY.finditer(str(node)):
            prefix=str(node)[:m.start()]
            if re.search(r'\b(?:fee|deposit|credit|discount)\s*(?:of|:)?\s*$',prefix,re.I):continue
            currency_prefix=re.search(r'\b(USD|AUD|NZD|CAD)\s*$',prefix,re.I)
            actual_currency=currency_prefix.group(1).upper() if currency_prefix else 'AUD'
            if actual_currency!=currency.upper():continue
            if Decimal(m.group(1).replace(',',''))==target: return parent
    return None

def rendered(source, raw, meta):
    if meta.get('status')!='ok' or meta.get('url')!=source.url:
        raise ValueError('Render metadata URL/status mismatch')
    if hashlib.sha256(raw).hexdigest()!=meta.get('sha256') or not meta.get('rendered_at'):
        raise ValueError('Render hash/date mismatch')
    markup=raw.decode('utf-8',errors='strict')
    soup=BeautifulSoup(markup,'html.parser')
    canonical=soup.find('link',rel='canonical')
    if not canonical or normalise_url(canonical.get('href',''))!=normalise_url(source.url):
        raise ValueError('Render canonical identity mismatch')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    if re.search(r'access denied|verify you are human|just a moment|404|captcha',title,re.I):
        raise ValueError('Blocked/error render')
    text=cleaned(markup)
    if len(text.split())<100 or not soup.body: raise ValueError('Thin render')
    return {'arm':'rendered_content_exposure','url':source.url,'html':markup,'clean':text,
            'source_sha256':sha(source.clean),'raw_sha256':sha(markup),'clean_sha256':sha(text),
            'evidence':[],'notes':{'rendered_at':meta['rendered_at'],'capture_sha256':meta['sha256'],
            'identity_check':'requested metadata and canonical URL match; historical final HTTP URL unavailable',
            'interpretation':'dated browser-content replacement; not isolated SSR','digit_repair':False}}

def semantic_rendered(source, raw, meta):
    """Semantics sensitivity variant: repair only unambiguous spaced currency digits."""
    out=rendered(source,raw,meta)
    clean=re.sub(r'(\$)\s*((?:\d\s*){2,})(?=\s*\*)',
                 lambda m:m.group(1)+re.sub(r'\s+','',m.group(2)),out['clean'])
    return {**out,'arm':'rendered_content_semantic','clean':clean,
            'clean_sha256':sha(clean),'notes':{**out['notes'],
            'digit_repair':'currency-only join of spaced digits before fare asterisk; raw capture retained',
            'interpretation':'semantic rendering sensitivity; not a pure rendering estimate'}}

def quoted(source, facts, arm, exclude_fact_ids=frozenset(), exclude_quotes=frozenset()):
    if arm not in ('page_grounded_faq','fare_clarification','structured_product_facts','verified_quantitative_facts'):
        raise ValueError('Inactive arm')
    # Excludes by fact_id (distinct facts already used) AND by exact quote text
    # (data/verified_facts.csv contains near-duplicate sliding-window rows that
    # expand to an identical sentence under different fact_ids -- found by
    # testing the combined stack, 2026-09-18; fact_id alone does not catch it).
    available=[e for e in evidence(source,facts)
               if e.fact_id not in exclude_fact_ids and e.quote not in exclude_quotes]
    raw=source.html;used=[];reason='no_locatable_verified_evidence'
    if arm=='page_grounded_faq':
        seen=set();groups={}
        for e in available:
            if e.quote in seen:continue
            seen.add(e.quote);used.append(e)
            # Group facts by a generic question so a page never repeats a question.
            question={'price':'What fares and conditions are stated on this page?',
                      'quantity':'What numerical information does this page provide?',
                      'date':'What dates does this page mention?'}.get(e.claim_type,'What further information does this page provide?')
            groups.setdefault(question,[]).append(e.quote)
            if len(used)==6:break
        bits=['<h3>'+html.escape(q)+'</h3>'+''.join('<blockquote>'+html.escape(t)+'</blockquote>' for t in quotes) for q,quotes in groups.items()]
        if bits:raw=append_body(raw,'<section id="geo-v3-faq"><h2>Frequently asked questions</h2>'+''.join(bits)+'</section>')
    elif arm=='fare_clarification':
        soup=BeautifulSoup(raw,'html.parser')
        for e in available:
            if e.claim_type!='price' or not re.search(r'\b(fare|flight)s?\b',e.quote,re.I):continue
            parent=fare_node(soup,e.value,e.unit,e.quote)
            if parent is None:continue
            block=soup.new_tag('section',id='geo-v3-fare');heading=soup.new_tag('h2');heading.string='Fare details and conditions'
            q=soup.new_tag('blockquote');q.string=e.quote;block.append(heading);block.append(q);parent.insert_after(block)
            raw=str(soup);used=[e];break
        reason='no_exact_visible_contextual_fare_anchor'
    else:
        # These additions are deterministic packaging of existing verified facts.
        # They never read evaluation queries or invent fields/values.
        selected=[e for e in available if e.claim_type in {'price','quantity','date','duration','inclusion'}]
        if arm=='verified_quantitative_facts':
            selected=[e for e in selected if e.claim_type in {'price','quantity','duration'} and re.search(r'\d',e.value or e.quote)]
        selected=selected[:8]
        if selected:
            tag='geo-v3-product-facts' if arm=='structured_product_facts' else 'geo-v3-quantitative-facts'
            title='Product facts' if arm=='structured_product_facts' else 'Verified quantitative facts'
            rows=[]
            for e in selected:
                label={'price':'Fare','quantity':'Quantity','duration':'Duration','date':'Date','inclusion':'Inclusion'}.get(e.claim_type,'Fact')
                rows.append('<dt>'+html.escape(label)+'</dt><dd>'+html.escape(e.quote)+'</dd>')
            raw=append_body(raw,'<section id="'+tag+'"><h2>'+title+'</h2><dl>'+''.join(rows)+'</dl></section>')
            used=selected
        reason='no_verified_eligible_fact'
    # Preserve exact baseline representation on no-op pages, without recleaning.
    text=cleaned(raw) if used else source.clean
    ledger=[asdict(e) for e in used];validate_evidence(source,ledger,facts)
    return {'arm':arm,'url':source.url,'html':raw,'clean':text,'source_sha256':sha(source.clean),
            'raw_sha256':sha(raw),'clean_sha256':sha(text),'evidence':ledger,
            'notes':{'unchanged_reason':reason if not used else '', 'inserted':bool(used),
                     'treatment':'verbatim evidence packaging; no invented facts or evaluation-query access'}}

def validate_output(output, expected):
    # Exact comparison includes bytes, provenance and ledger, not self-report hashes.
    if output!=expected: raise ValueError('Output differs from authorised deterministic transformation')
    if sha(output['html'])!=output['raw_sha256'] or sha(output['clean'])!=output['clean_sha256']:
        raise ValueError('Output content hash mismatch')

def full_stack(source, raw, meta, facts, external=None):
    """Compose the five ACTUALLY-SELECTED content interventions (matching
    ALL_METHOD_RESULTS_2026-09-13.md / RETAINED_METHODS_CRITICAL_REVIEW_2026-09-14.md
    / the main deck's Schema markup slides), not their earlier or base variants.

    Deduplicates shared verified facts across FAQ / structured facts / schema:
    each is grounded in the same fact table, and a fact eligible for more than
    one of them was found (2026-09-14 review) to get quoted twice on 31/52
    pages if simply appended independently. Order below decides precedence --
    FAQ first (the strongest individual fixed-layer result), then structured
    facts, then schema -- each later step excludes fact_ids already used.
    External attribution draws from a disjoint fact table (external_facts.csv,
    not verified_facts.csv) so it cannot collide with the other three and is
    run last, after the page structure it anchors against (the fee notice) is
    in its final form.
    """
    from .rendered_organisation import organise_rendered
    from .faq_refinement import refined_faq
    from .schema_structured import structured_schema
    from geo_bench.config import CONFIG as GEO_CONFIG
    # geo_bench/generation/prompts.py build_prompt() does a raw p.text[:budget]
    # slice on EVERY candidate document for the fixed layer (budget =
    # page_prompt_chars = 24000), applied identically to every brand. A page
    # built past that length does not error -- it silently loses whatever
    # text sits after char 24000. Found by dry-running the corrected stack
    # against all 52 real pages (2026-09-18): 2/52 (the unusually long
    # /au/th and /au/vn guide pages) exceed 24000 chars once all five
    # components are appended, which would silently truncate the
    # last-appended component with no error and no trace. Stop appending
    # once the budget is reached instead, and record exactly what was
    # skipped -- an honest, disclosed no-op is preferable to a silent cut.
    budget=int(GEO_CONFIG.page_prompt_chars)
    used_fact_ids=set();used_quotes=set()
    def _track(step_evidence):
        for e in step_evidence:
            if e.get('fact_id'):used_fact_ids.add(e['fact_id'])
            if e.get('quote'):used_quotes.add(e['quote'])
    components=[];skipped=[]

    def _try_commit(name,build_fn):
        """Build a candidate step; commit only if the RESULTING length still
        fits the budget (checked after building, not before -- a step can be
        the one that tips the total over, and must not be committed on the
        strength of the pre-step length alone). Reverts (keeps `current`
        unchanged) and records a skip otherwise, so a later, smaller
        component still gets a fair chance rather than the whole stack
        collapsing once one step doesn't fit."""
        nonlocal current
        candidate=build_fn()
        candidate_source=Source(source.url,candidate['html'],source.clean)
        if len(cleaned(candidate_source.html))<=budget:
            current=candidate_source
            _track(candidate.get('evidence') or [])
            components.append(name)
        else:
            skipped.append(name)

    rendered_out=organise_rendered(source, raw, meta)
    current=Source(source.url,rendered_out['html'],source.clean)
    if len(cleaned(current.html))>budget:
        # Even the rendered-only base exceeds the fixed-layer budget on this
        # page (found on /au/th during audit -- its standalone
        # rendered_content_organised result is 24,644 chars, already over
        # the 24,000 cap, meaning that already-reported result silently lost
        # its last ~600 characters to build_prompt()'s raw slice; disclosed
        # here, not silently repeated). Nothing later in the chain can fit
        # either. Leave the page as a clean, disclosed no-op -- the same
        # convention every other arm in this codebase already uses for a
        # page it cannot legitimately treat, rather than crash the whole
        # 52-page batch on one oversized page or ship something that will
        # just get silently truncated downstream anyway.
        base_len=len(cleaned(current.html))
        return {'arm':'full_stack_exploratory','url':source.url,'html':source.html,
                'clean':source.clean,'source_sha256':sha(source.clean),
                'raw_sha256':sha(source.html),'clean_sha256':sha(source.clean),'evidence':[],
                'notes':{'composite_stack':True,'components':[],'components_skipped_over_budget':
                ['rendered_content_organised','page_grounded_faq_refined','structured_product_facts',
                 'schema_structured_markup','external_source_attribution_refined'],
                'unchanged_reason':f'rendered_content_organised alone is {base_len} chars, '
                                   f'over the {budget}-char fixed-layer budget',
                'page_prompt_chars_budget':budget,'final_clean_chars':len(source.clean),
                'fare_included':False,'position_control_included':False,'autogeo_included':False}}
    components.append('rendered_content_organised')

    _try_commit('page_grounded_faq_refined', lambda: refined_faq(current,facts))
    _try_commit('structured_product_facts', lambda: quoted(
        current,facts,'structured_product_facts',
        exclude_fact_ids=used_fact_ids,exclude_quotes=used_quotes))
    _try_commit('schema_structured_markup', lambda: structured_schema(
        current,facts,exclude_fact_ids=used_fact_ids,exclude_quotes=used_quotes))
    if external is not None:
        from .external_refinement import refined_external
        _try_commit('external_source_attribution_refined', lambda: refined_external(current,external))

    text=cleaned(current.html)
    assert len(text)<=budget, 'commit-or-revert invariant violated: final text exceeds budget'
    return {'arm':'full_stack_exploratory','url':source.url,'html':current.html,
            'clean':text,'source_sha256':sha(source.clean),'raw_sha256':sha(current.html),
            'clean_sha256':sha(text),'evidence':[],'notes':{'composite_stack':True,
            'components':components,'components_skipped_over_budget':skipped,
            'page_prompt_chars_budget':budget,'final_clean_chars':len(text),
            'deduplication':'faq_first_then_structured_then_schema; excludes by fact_id AND exact quote text',
            'shared_fact_ids_used_once':sorted(used_fact_ids),
            'shared_quotes_used_once':len(used_quotes),
            'fare_included':False,'position_control_included':False,'autogeo_included':False}}

def autogeo_rewrite(source, rewritten_html, rewrite_meta):
    """Validate an externally produced automatic rewrite as a separate exploratory arm.

    This function does not call a model. It only admits a frozen rewrite after
    identity, provenance and conservative fact-preservation checks pass.
    """
    if rewrite_meta.get('source_url')!=source.url or not rewrite_meta.get('rewriter_model'):
        raise ValueError('AutoGEO provenance or source identity missing')
    text=cleaned(rewritten_html)
    if len(text.split())<100: raise ValueError('AutoGEO rewrite is thin')
    # Every numeric token in the rewrite must occur in the source representation;
    # this blocks invented prices, dates and quantities while allowing prose edits.
    nums=set(re.findall(r'\d[\d,.%]*',text)); source_nums=set(re.findall(r'\d[\d,.%]*',source.clean))
    if not nums.issubset(source_nums): raise ValueError('AutoGEO introduced unsupported numeric value')
    return {'arm':'autogeo_rewrite_exploratory','url':source.url,'html':rewritten_html,
            'clean':text,'source_sha256':sha(source.clean),'raw_sha256':sha(rewritten_html),
            'clean_sha256':sha(text),'evidence':[],
            'notes':{'composite_rewrite':True,'evaluation_query_access':False,
                     'fact_preservation':'numeric-token subset check; independent factual review required',
                     'rewriter_model':rewrite_meta['rewriter_model'],'rewritten_at':rewrite_meta.get('rewritten_at','')}}
