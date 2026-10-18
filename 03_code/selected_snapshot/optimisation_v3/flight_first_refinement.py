"""Query-blind r5: expose captured FAQ labels and move FAQs before tourism.

Only already-expanded, structurally paired FAQ controls are converted. No
facts, prices, summaries, questions or ranking instructions are generated.
"""
from collections import Counter
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from geo_bench.retrieval.cleaner import clean_html
from .arms import cleaned, sha

ARM = 'v3_final_flight_first_r5'


def direct_child(node, main):
    while node.parent is not main:
        if node.parent is None:
            raise ValueError('Section outside main')
        node = node.parent
    return node


def refine(prior):
    if prior['arm'] != 'v3_final_core' or sha(prior['html']) != prior['raw_sha256'] or sha(prior['clean']) != prior['clean_sha256']:
        raise ValueError('Invalid r4 input identity')
    if cleaned(prior['html']) != prior['clean']:
        raise ValueError('Input extraction mismatch')
    soup = BeautifulSoup(prior['html'], 'html.parser')
    if soup.select('[data-geo-r5-question]'):
        raise ValueError('Already refined')
    body_before, jsonld_before = clean_html(prior['html'])
    cards_before = Counter(str(x) for x in soup.select('[data-sku]'))
    links_before = Counter((a.get('href'), a.get_text(' ',strip=True)) for a in soup.find_all('a'))
    entries, moves, skipped = [], [], []
    if urlsplit(prior['url']).path.startswith('/flights/'):
        for button in soup.select('button[data-testid="AccordionTitle"]'):
            question = ' '.join(button.get_text(' ',strip=True).split())
            if '?' not in question:
                continue
            heading = button.parent
            accordion = button.find_parent(attrs={'data-testid':'Accordion'})
            answers = accordion.select('[data-testid="AccordionContent"]') if accordion else []
            if (button.get('aria-expanded') != 'true' or heading.name != 'h3'
                    or ' '.join(heading.get_text(' ',strip=True).split()) != question or len(answers) != 1
                    or not button.find_parent('main')):
                skipped.append({'question':question,'reason':'unsupported_or_closed_FAQ'})
                continue
            answer = answers[0]
            if any(a.has_attr('hidden') or a.get('aria-hidden')=='true' or
                   'display:none' in a.get('style','').replace(' ','').lower()
                   for a in [answer, *answer.parents]):
                skipped.append({'question':question,'reason':'hidden_answer'})
                continue
            answer_text = cleaned(str(answer))
            if not answer_text:
                raise ValueError('Empty paired FAQ answer')
            entry = {'question':question,'answer':answer_text,'answer_html_sha256':sha(str(answer)),
                     'question_html_sha256':sha(str(button)), 'r4_html_sha256':prior['raw_sha256']}
            # Preserve the h3 and all captured text, but remove the interactive
            # element that the unchanged common cleaner treats as boilerplate.
            button.name = 'span'
            for attribute in ('type','tabindex','aria-expanded','aria-disabled','disabled','role'):
                button.attrs.pop(attribute,None)
            button['data-geo-r5-question'] = str(len(entries))
            entries.append(entry)

        for main in soup.find_all('main'):
            tourism = []
            faqs = []
            for h in main.find_all('h2'):
                text = h.get_text(' ',strip=True).lower()
                if text.startswith('explore '):
                    tourism.append(direct_child(h,main))
                if 'frequently asked questions' in text and h.find_parent(attrs={'data-testid':'AccordionTabsContainer'}):
                    faqs.append(direct_child(h,main))
            tourism = list({id(n):n for n in tourism}.values())
            faqs = list({id(n):n for n in faqs}.values())
            if not tourism or not faqs:
                continue
            if len(tourism)!=1 or len(faqs)!=1 or tourism[0] is faqs[0]:
                raise ValueError('Ambiguous tourism/FAQ section boundary')
            travel, faq = tourism[0], faqs[0]
            children = list(main.children)
            pos = lambda n: next(i for i,c in enumerate(children) if c is n)
            if pos(faq) < pos(travel):
                continue
            before = str(faq)
            travel.insert_before(faq.extract())
            if str(faq)!=before:
                raise ValueError('FAQ section changed while moving')
            moves.append({'faq_section_sha256':sha(before),'policy':'FAQ before Explore section'})

    markup = str(soup) if entries or moves else prior['html']
    body_after, jsonld_after = clean_html(markup)
    extra_words = Counter(' '.join(e['question'] for e in entries).split())
    if Counter(body_after.split()) != Counter(body_before.split()) + extra_words:
        raise ValueError('Body content changed beyond preserved FAQ labels')
    if jsonld_before != jsonld_after:
        raise ValueError('Metadata changed')
    if Counter(str(x) for x in soup.select('[data-sku]')) != cards_before:
        raise ValueError('Offer card changed')
    if Counter((a.get('href'),a.get_text(' ',strip=True)) for a in soup.find_all('a')) != links_before:
        raise ValueError('Source link changed')
    for node, entry in zip(soup.select('[data-geo-r5-question]'), entries):
        answer = node.find_parent(attrs={'data-testid':'Accordion'}).select_one('[data-testid="AccordionContent"]')
        if sha(str(answer)) != entry['answer_html_sha256']:
            raise ValueError('Paired answer changed')
        if (entry['question']+' '+entry['answer']) not in body_after:
            raise ValueError('Question and answer not adjacent after extraction: '+repr(entry['question'])+' / '+repr(entry['answer'][:120]))
    text = cleaned(markup)
    return {**prior,'arm':ARM,'html':markup,'clean':text,'raw_sha256':sha(markup),'clean_sha256':sha(text),
            'evidence':prior['evidence']+[{'kind':'r5_faq_restoration','r4_html_sha256':prior['raw_sha256'],'pairs':entries}],
            'notes':{**prior['notes'],'r4_clean_sha256':prior['clean_sha256'],'query_access':False,
                     'r5':{'restored_questions':len(entries),'movements':moves,'skipped':skipped},
                     'interpretation':'r4 plus captured FAQ question labels and FAQ-before-tourism ordering; exploratory development treatment'}}
