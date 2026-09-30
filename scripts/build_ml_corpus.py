"""Freeze a CC BY 4.0 PMC paragraph snapshot for source-separated ML review.

Run explicitly once into a new output path. Never retain downloaded full XML.
Selection and exclusions are recorded, and the official PMC limit is 3 rps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from biosure.schema import canonical_bytes

QUERY = '(organ-on-a-chip[Title/Abstract] OR microphysiological[Title/Abstract]) AND cc by license[Filter]'
LICENSE = 'https://creativecommons.org/licenses/by/4.0/'
MAX_XML = 4_000_000
SELECTION = 'First 24 eligible unique articles in first 36 eSearch results, publication-date order; first eight unique body paragraphs, 80-3000 characters.'


def _name(element: ET.Element) -> str:
    return element.tag.rsplit('}',1)[-1]


def _text(element: ET.Element) -> str:
    return ' '.join(''.join(element.itertext()).split())


def _descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if _name(child) == name]


def _id(meta: ET.Element, kind: str) -> str:
    return next((_text(x) for x in _descendants(meta,'article-id') if x.get('pub-id-type') == kind), '')


def extract_source(xml_bytes: bytes, pmcid: str) -> dict:
    if not re.fullmatch(r'PMC[0-9]+',pmcid) or len(xml_bytes)>MAX_XML:
        raise ValueError('invalid PMCID or XML size')
    root = ET.fromstring(xml_bytes)
    articles = _descendants(root,'article')
    if len(articles)!=1:
        raise ValueError('expected one JATS article')
    article = articles[0]
    fronts = [item for item in article if _name(item)=='front']
    bodies = [item for item in article if _name(item)=='body']
    if len(fronts)!=1 or len(bodies)!=1:
        raise ValueError('unique article front/body required')
    metas = _descendants(fronts[0],'article-meta')
    if len(metas)!=1 or _id(metas[0],'pmcid')!=pmcid:
        raise ValueError('PMCID mismatch')
    meta=metas[0]
    licenses=[_text(item).replace('http://','https://',1).rstrip('/')+'/' for item in _descendants(meta,'license_ref')]
    if LICENSE not in licenses:
        raise ValueError('explicit CC BY 4.0 license required')
    doi=_id(meta,'doi')
    titles=_descendants(meta,'article-title')
    if not doi or len(titles)!=1:
        raise ValueError('DOI and title required')
    authors=[]
    for contrib in _descendants(meta,'contrib'):
        if contrib.get('contrib-type')!='author':
            continue
        names=_descendants(contrib,'name')
        if names:
            authors.append(' '.join(_text(part) for part in names[0] if _text(part)) or _text(names[0]))
    if not authors:
        raise ValueError('attributed authors required')
    paragraphs=[]
    seen=set()
    excluded={'fig','table-wrap','ref-list','caption','boxed-text','supplementary-material'}
    number=0

    def walk(node: ET.Element, blocked: bool=False) -> None:
        nonlocal number
        label=_name(node)
        blocked=blocked or label in excluded
        if label=='p':
            number+=1
            text=_text(node)
            digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
            if not blocked and 80<=len(text)<=3000 and digest not in seen and len(paragraphs)<8:
                seen.add(digest)
                paragraphs.append({'locator':f'body//p[{number}]','text':text})
        for child in node:
            walk(child,blocked)

    walk(bodies[0])
    if len(paragraphs)<8:
        raise ValueError('fewer than eight eligible unique body paragraphs')
    source_url=f'https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmcid[3:]}&metadataPrefix=pmc'
    return {'pmcid':pmcid,'doi':doi,'title':_text(titles[0]),'authors':authors,
            'license_uri':LICENSE,'article_url':f'https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/',
            'source_url':source_url,'source_sha256':hashlib.sha256(xml_bytes).hexdigest(),
            'paragraphs':paragraphs}


def collect(*, limit: int=24) -> dict:
    if not 1<=limit<=24:
        raise ValueError('limit must be 1-24')
    query_url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode(
        {'db':'pmc','term':QUERY,'retmax':36,'retmode':'json','sort':'pub date'})
    request=urllib.request.Request(query_url,headers={'User-Agent':'BioSURE-corpus/0.3'})
    with urllib.request.urlopen(request,timeout=30) as response:
        search=json.load(response)['esearchresult']
    ids=search['idlist']
    collected=[]; exclusions=[]
    for ident in ids:
        if len(collected)>=limit:
            break
        pmcid='PMC'+ident
        source_url=f'https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{ident}&metadataPrefix=pmc'
        try:
            request=urllib.request.Request(source_url,headers={'User-Agent':'BioSURE-corpus/0.3'})
            with urllib.request.urlopen(request,timeout=30) as response:
                raw=response.read(MAX_XML+1)
            source=extract_source(raw,pmcid)
            collected.append(source)
            print(f'Accepted {len(collected)}/{limit}: {pmcid}',flush=True)
        except (OSError,ET.ParseError,ValueError) as error:
            exclusions.append({'pmcid':pmcid,'reason':type(error).__name__+': '+str(error)[:120]})
            print(f'Excluded {pmcid}: {type(error).__name__}',flush=True)
        time.sleep(.4)
    if len(collected)<8:
        raise ValueError('fewer than eight eligible articles; no evaluation artifact created')
    return {'schema_version':'biosure.ml-corpus/1.0','snapshot':'2026-09-30','query':QUERY,
            'selection':SELECTION,'search_url':query_url,'search_result_ids':['PMC'+ident for ident in ids],
            'exclusions':exclusions,'change_notice':'Selected paragraphs are excerpted from attributed CC BY 4.0 JATS; experiment variants are constructed alterations and not original article claims. Snapshot may not reflect latest NLM data.',
            'articles':collected}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('output exists; corpus snapshots are not overwritten')
    corpus=collect()
    with args.output.open('xb') as handle:
        handle.write(canonical_bytes(corpus))
    print(f"Frozen {len(corpus['articles'])} distinct licensed sources",flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
