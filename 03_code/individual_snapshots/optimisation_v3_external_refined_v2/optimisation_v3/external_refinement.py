"""Contextual primary-source statistic, separate from fare claims."""
from bs4 import BeautifulSoup
from .remaining import attribution_block,result

def refined_external(source,external):
    soup=BeautifulSoup(source.html,'html.parser')
    headings=soup.find_all('h1')
    block,ledger,match=attribution_block(source,external,True)
    eligible=bool(block) and len(headings)==1 and 'sydney' in headings[0].get_text(' ',strip=True).lower()
    raw=source.html
    if eligible:
        block=block.replace('<blockquote>','<h2>Sydney Airport context</h2><blockquote>',1)
        node=BeautifulSoup(block,'html.parser').section
        # Place after the complete heading container, keeping price and nearby fees intact.
        anchor=headings[0]
        while anchor.parent and anchor.parent.name not in ('body','main'):
            if len(anchor.parent.get_text(' ',strip=True))>1800:break
            anchor=anchor.parent
        notices=[n for n in soup.find_all(attrs={'data-testid':'AlertBody'}) if 'Fees are applied once at checkout.' in n.get_text(' ',strip=True)]
        if len(notices)>1:raise ValueError('Ambiguous fee notice placement')
        if notices:
            anchor=notices[0]
            while anchor.parent and anchor.parent.name not in ('body','main') and anchor.parent.get_text(' ',strip=True)==anchor.get_text(' ',strip=True):
                anchor=anchor.parent
        anchor.insert_after(node);raw=str(soup)
    return result(source,'external_source_attribution_refined',raw,ledger if eligible else [],{
        'inserted':eligible,'entity_evidence':match,'placement':'after complete fee notice where present; otherwise bounded heading container',
        'interpretation':'airport context statistic plus attribution and placement; not fare evidence or isolated citation effect',
        'unchanged_reason':'' if eligible else 'no_unique_Sydney_heading_and_airport_evidence'})
