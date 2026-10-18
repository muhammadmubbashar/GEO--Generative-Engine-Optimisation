"""Query-independent page identity metadata; original body/graph values retained."""
import json
import re
from bs4 import BeautifulSoup
from .arms import cleaned, sha
from geo_bench.retrieval.cleaner import clean_html
from geo_bench.search.live_retriever import normalise_url

ARM = 'schema_page_identity'
SCRIPT = re.compile(r'<script\b[^>]*>.*?</script\s*>', re.I | re.S)
PAGE_TYPES = {'WebPage', 'FAQPage', 'CollectionPage', 'ItemPage', 'AboutPage', 'ContactPage'}

def objects(raw):
    """Find exact JSON object byte spans without reserializing existing values."""
    decoder = json.JSONDecoder()
    quoted=False;escaped=False
    for start,char in enumerate(raw):
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
            continue
        if char=='"':quoted=True;continue
        if char!='{':continue
        try:
            value, end = decoder.raw_decode(raw, start)
        except ValueError:
            continue
        if isinstance(value, dict):
            yield start, end, value

def schema_identity(source):
    raw = source.html
    soup = BeautifulSoup(raw, 'html.parser')
    body, graph = clean_html(raw)
    if (body + ' ' + graph).strip() != source.clean:
        raise ValueError('Schema baseline extraction mismatch')
    def finish(markup=raw, fields=None, reason='', mode='noop'):
        fields = fields or {}
        text = cleaned(markup) if fields else source.clean
        assert clean_html(markup)[0] == body, 'Schema changed visible content'
        return {'arm':ARM,'url':source.url,'html':markup,'clean':text,
                'source_sha256':sha(source.clean),'raw_sha256':sha(markup),'clean_sha256':sha(text),
                'evidence':[], 'notes':{'inserted':bool(fields),'fields':fields,'mode':mode,
                'reason':reason,'body_sha256':sha(body),
                'name_source':name if fields else '',
                'interpretation':'missing page identity JSON-LD; body unchanged; serialized text consumer, not graph-aware ranking'}}
    name = ''
    if soup.find(id='geo-schema-page-identity'):
        return finish(reason='already_transformed')
    canonical = soup.find('link',rel='canonical')
    if canonical and normalise_url(canonical.get('href','')) != normalise_url(source.url):
        return finish(reason='mismatched_canonical')
    headings = soup.find_all('h1')
    if len(headings) != 1:
        return finish(reason='ambiguous_heading')
    heading = headings[0]
    for a in [heading]+list(heading.parents):
        if a.has_attr('hidden') or a.get('aria-hidden') == 'true' or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',a.get('style',''),re.I):
            return finish(reason='hidden_heading')
    name = heading.get_text(' ',strip=True)
    # Identity only: an H1 amount is not a new Offer or unconditional price.
    name = re.split(r'\s+(?:AU|A|US|NZ)?\$|\s+AUD\s',name,maxsplit=1)[0].strip()
    if not name or name not in body or len(name)>250:
        return finish(reason='heading_not_grounded')
    scripts=[];page_nodes=[];ids=set()
    for m in SCRIPT.finditer(raw):
        tag=BeautifulSoup(m.group(),'html.parser').find('script')
        if tag.get('type','').lower()!='application/ld+json':continue
        offset=m.start()+m.group().index('>')+1
        content=raw[offset:m.end()-len(re.search(r'</script\s*>$',m.group(),re.I).group())]
        try:json.loads(content)
        except ValueError:return finish(reason='invalid_existing_jsonld')
        scripts.append(content)
        for start,end,obj in objects(content):
            if isinstance(obj.get('@id'),str):ids.add(obj['@id'])
            types=obj.get('@type',[]);types=[types] if isinstance(types,str) else types
            if any(t in PAGE_TYPES for t in types):page_nodes.append((offset+start,obj))
    if len(page_nodes)>1:return finish(reason='ambiguous_existing_page_nodes')
    identity=source.url+'#geo-webpage'
    if page_nodes:
        start,node=page_nodes[0]
        if node.get('url') and (not isinstance(node['url'],str) or normalise_url(node['url'])!=normalise_url(source.url)):
            return finish(reason='existing_page_url_conflict')
        fields={k:v for k,v in {'@id':identity,'url':source.url,'name':name}.items() if k not in node}
        if '@id' in fields and identity in ids:return finish(reason='existing_id_collision')
        if not fields:return finish(reason='page_identity_already_present')
        # Only insert new properties; all original JSON and HTML bytes stay intact.
        prefix=json.dumps(fields,ensure_ascii=False,separators=(',',':'))[1:-1]+','
        prefix=prefix.replace('<','\\u003c')
        result=raw[:start+1]+prefix+raw[start+1:]
        return finish(result,fields,mode='enrich_existing_page_node')
    if identity in ids:return finish(reason='existing_id_collision')
    fields={'@context':'https://schema.org','@type':'WebPage','@id':identity,'url':source.url,'name':name}
    payload=json.dumps(fields,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    block='<script id="geo-schema-page-identity" type="application/ld+json">'+payload+'</script>'
    i=raw.lower().rfind('</head>')
    if i<0:return finish(reason='missing_head')
    return finish(raw[:i]+block+raw[i:],fields,mode='add_missing_webpage')
