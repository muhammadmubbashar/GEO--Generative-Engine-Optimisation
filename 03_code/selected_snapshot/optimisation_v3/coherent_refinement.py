"""Versioned, query-blind content refinements. No ranking or generation access."""
from collections import Counter
import html
import re
from bs4 import BeautifulSoup
from .arms import semantic_rendered, cleaned, sha
from .rendered_organisation import repair_currency
from .remaining import result, entity_match

RENDERED_ARM = 'rendered_content_coherent_v2'
EXTERNAL_ARM = 'external_source_useful_v3'
RULES = (
    ('mc-deals-section', 'mc-faqs-section'),
    ('rtw-deals-section', 'rtw-faqs-section'),
    ('cot-air-transportation-deals', 'cot-faqs-section'),
)

def coherent_rendered(source, raw, meta):
    original = semantic_rendered(source, raw, meta)
    soup = BeautifulSoup(original['html'], 'html.parser')
    moves = []
    for offer_id, faq_id in RULES:
        offers = soup.find_all(attrs={'data-testid': offer_id})
        faqs = soup.find_all(attrs={'data-testid': faq_id})
        if not offers or not faqs:
            continue
        if len(offers) != 1 or len(faqs) != 1:
            raise ValueError('Ambiguous section anchors')
        offer, faq = offers[0], faqs[0]
        if not offer.select('[data-sku]'):
            continue
        main = offer.find_parent('main')
        if main is None or faq.find_parent('main') is not main or offer in faq.parents or faq in offer.parents:
            raise ValueError('Unsafe section movement')
        order = list(main.descendants)
        if next(i for i, n in enumerate(order) if n is offer) > next(i for i, n in enumerate(order) if n is faq):
            continue
        subtree = str(offer)
        # A visible contents link preserves discoverability of the relocated section.
        # Its label is taken verbatim from the existing heading, never from a query.
        heading = offer.find(['h2', 'h3'])
        label = heading.get_text(' ', strip=True) if heading else ''
        contents = None
        if label:
            contents = soup.new_tag('p', attrs={'data-geo-contents': offer_id})
            contents.append('On this page: ')
            anchor = soup.new_tag('a', href='#geo-' + offer_id)
            anchor.string = label
            contents.append(anchor)
            offer.insert_before(contents)
        faq.insert_after(offer.extract())
        if str(offer) != subtree:
            raise ValueError('Offer subtree changed')
        # Add only an anchor attribute; card text, fares and restrictions are untouched.
        offer['id'] = offer.get('id') or 'geo-' + offer_id
        if contents:
            contents.a['href'] = '#' + offer['id']
        moves.append({'offer': offer_id, 'after': faq_id, 'contents_label': label,
                      'original_subtree_sha256': sha(subtree)})
    markup = str(soup) if moves else original['html']
    text = repair_currency(cleaned(markup)) if moves else original['clean']
    audit = BeautifulSoup(markup, 'html.parser')
    for node in audit.select('[data-geo-contents]'):
        node.decompose()
    if Counter(repair_currency(cleaned(str(audit))).split()) != Counter(original['clean'].split()):
        raise ValueError('Lost or changed source words')
    before_cards = [str(x) for x in BeautifulSoup(original['html'], 'html.parser').select('[data-sku]')]
    after_cards = [str(x) for x in soup.select('[data-sku]')]
    if Counter(before_cards) != Counter(after_cards):
        raise ValueError('Offer cards changed')
    return {**original, 'arm': RENDERED_ARM, 'html': markup, 'clean': text,
            'raw_sha256': sha(markup), 'clean_sha256': sha(text),
            'notes': {**original['notes'], 'movements': moves, 'query_access': False,
                      'interpretation': 'dated rendered content, currency repair, contiguous explanation and FAQ sections, and verbatim section contents links; exploratory'}}

def useful_external(source, evidence):
    soup = BeautifulSoup(source.html, 'html.parser')
    headings = soup.find_all('h1')
    match = entity_match(source)
    eligible = bool(match) and len(headings) == 1 and 'sydney' in headings[0].get_text(' ', strip=True).lower()
    if not eligible:
        return result(source, EXTERNAL_ARM, source.html, [], {'inserted': False, 'query_access': False})
    if soup.find(id='geo-external-useful'):
        raise ValueError('External block already present')
    title = headings[0].get_text(' ', strip=True)
    # Route identity only: do not repeat a headline fare without its qualifiers.
    title = re.sub(r'\s*\$.*$', '', title).strip()
    block = ('<section id="geo-external-useful"><h2>' + html.escape(title) +
             ': Sydney Airport access</h2><p>For the Sydney Airport part of this journey, the airport operator states:</p>' +
             '<blockquote>' + html.escape(evidence['quote']) + '</blockquote><p>Source: <a href="' +
             html.escape(evidence['source_url'], quote=True) + '">Sydney Airport — Transport options</a>. ' +
             'Airport access information; ground transport is separate from the airfare. Check the operator for current services.</p></section>')
    # Keep complete fare/fee containers intact. Never inject inside a price sentence.
    notices = [x for x in soup.find_all(attrs={'data-testid': 'AlertBody'})
               if 'Fees are applied once at checkout.' in x.get_text(' ', strip=True)]
    if len(notices) > 1:
        raise ValueError('Ambiguous fee notice')
    anchor = notices[0] if notices else headings[0]
    if not notices:
        while anchor.parent and anchor.parent.name not in ('body', 'main'):
            if len(anchor.parent.get_text(' ', strip=True)) > 1800:
                break
            anchor = anchor.parent
    else:
        while anchor.parent and anchor.parent.name not in ('body', 'main') and anchor.parent.get_text(' ', strip=True) == anchor.get_text(' ', strip=True):
            anchor = anchor.parent
    anchor.insert_after(BeautifulSoup(block, 'html.parser').section)
    raw = str(soup)
    soup.find(id='geo-external-useful').decompose()
    if cleaned(str(soup)) != cleaned(source.html):
        raise ValueError('External insertion changed original source text')
    return result(source, EXTERNAL_ARM, raw, [evidence], {
        'inserted': True, 'entity_evidence': match, 'query_access': False,
        'interpretation': 'practical primary-source fact plus attribution and page-derived scope heading; replaces annual traffic statistic; exploratory',
        'placement': 'after complete fee notice or bounded heading container'})
